/**
 * WebRTC audio/video call service.
 *
 * Manages a single peer-to-peer call launched from the support chat. Signaling
 * (SDP offer/answer + ICE candidates) is relayed through the Socket.IO server
 * (see backend/websocket_manager.py webrtc_* handlers); media flows directly
 * peer-to-peer.
 *
 * NOTE: getUserMedia + RTCPeerConnection require a secure context — HTTPS or
 * localhost. On a plain-HTTP LAN origin (e.g. http://192.168.x.x) the browser
 * blocks mic/cam access and startCall/acceptCall will reject with a clear error.
 */
import { socketService } from './socketService';

export type CallState =
    | 'idle'
    | 'calling'     // we sent an offer, waiting for callee
    | 'ringing'     // we received an offer, user must accept/reject
    | 'connecting'  // answered, establishing peer connection
    | 'in-call';

export interface IncomingCallInfo {
    callId: string;
    from: string;        // caller username
    fromName: string;    // caller display name
    convoId: string;
    video: boolean;
}

export interface PeerInfo {
    username: string;
    name: string;
    convoId: string;
}

type Handlers = {
    onStateChange?: (state: CallState, peer: PeerInfo | null) => void;
    onIncomingCall?: (info: IncomingCallInfo) => void;
    onLocalStream?: (stream: MediaStream | null) => void;
    onRemoteStream?: (stream: MediaStream | null) => void;
    onError?: (message: string) => void;
};

const ICE_SERVERS: RTCIceServer[] = [
    { urls: 'stun:stun.l.google.com:19302' },
    { urls: 'stun:stun1.l.google.com:19302' },
];

function uuid(): string {
    if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID();
    return 'call-' + Date.now() + '-' + Math.random().toString(36).slice(2, 10);
}

class WebRTCCallService {
    private pc: RTCPeerConnection | null = null;
    private localStream: MediaStream | null = null;
    private remoteStream: MediaStream | null = null;

    private state: CallState = 'idle';
    private peer: PeerInfo | null = null;
    private callId = '';
    private isVideo = false;

    // Buffer ICE candidates that arrive before the remote description is set.
    private pendingCandidates: RTCIceCandidateInit[] = [];
    private remoteDescSet = false;

    private handlers: Handlers = {};
    private initialized = false;

    /** Register socket signaling listeners. Idempotent — safe to call on every app mount. */
    init() {
        if (this.initialized) return;
        this.initialized = true;
        socketService.on('webrtc_offer', (d: any) => this.onOffer(d));
        socketService.on('webrtc_answer', (d: any) => this.onAnswer(d));
        socketService.on('webrtc_ice', (d: any) => this.onRemoteIce(d));
        socketService.on('webrtc_call_reject', (d: any) => this.onRejected(d));
        socketService.on('webrtc_call_end', (d: any) => this.onRemoteEnd(d));
        socketService.on('webrtc_unavailable', (d: any) => this.onUnavailable(d));
    }

    setHandlers(h: Handlers) {
        this.handlers = h;
    }

    getState(): CallState { return this.state; }
    getPeer(): PeerInfo | null { return this.peer; }

    private setState(s: CallState) {
        this.state = s;
        this.handlers.onStateChange?.(s, this.peer);
    }

    private assertSecureMedia() {
        if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
            throw new Error(
                'Camera/microphone are unavailable. Calls require a secure connection (HTTPS or localhost).'
            );
        }
    }

    // ── Outgoing call ─────────────────────────────────────────────────────────

    async startCall(to: string, toName: string, convoId: string, video: boolean, fromName: string) {
        if (this.state !== 'idle') {
            this.handlers.onError?.('A call is already in progress.');
            return;
        }
        try {
            this.assertSecureMedia();
            this.isVideo = video;
            this.callId = uuid();
            this.peer = { username: to, name: toName, convoId };
            this.setState('calling');

            await this.setupPeer(video);
            const offer = await this.pc!.createOffer();
            await this.pc!.setLocalDescription(offer);

            socketService.sendCallSignal('webrtc_offer', {
                to,
                convo_id: convoId,
                call_id: this.callId,
                media: video ? 'video' : 'audio',
                from_name: fromName,   // caller's display name, shown to the callee
                sdp: offer,
            });
        } catch (e: any) {
            this.handlers.onError?.(e?.message || 'Failed to start call.');
            this.cleanup();
        }
    }

    // ── Incoming call ─────────────────────────────────────────────────────────

    private async onOffer(d: any) {
        // Ignore a second incoming offer while busy — auto-reject.
        if (this.state !== 'idle') {
            socketService.sendCallSignal('webrtc_call_reject', { to: d.from, call_id: d.call_id });
            return;
        }
        this.callId = d.call_id;
        this.isVideo = d.media === 'video';
        this.peer = { username: d.from, name: d.from_name || d.from, convoId: d.convo_id || '' };
        // Stash the remote offer until the user accepts.
        this.pendingOffer = d.sdp;
        this.setState('ringing');
        this.handlers.onIncomingCall?.({
            callId: d.call_id,
            from: d.from,
            fromName: d.from_name || d.from,
            convoId: d.convo_id || '',
            video: this.isVideo,
        });
    }
    private pendingOffer: RTCSessionDescriptionInit | null = null;

    async acceptCall() {
        if (this.state !== 'ringing' || !this.pendingOffer || !this.peer) return;
        try {
            this.assertSecureMedia();
            this.setState('connecting');
            await this.setupPeer(this.isVideo);
            await this.pc!.setRemoteDescription(new RTCSessionDescription(this.pendingOffer));
            this.remoteDescSet = true;
            await this.flushPendingCandidates();

            const answer = await this.pc!.createAnswer();
            await this.pc!.setLocalDescription(answer);
            socketService.sendCallSignal('webrtc_answer', {
                to: this.peer.username,
                call_id: this.callId,
                sdp: answer,
            });
            this.pendingOffer = null;
            this.setState('in-call');
        } catch (e: any) {
            this.handlers.onError?.(e?.message || 'Failed to accept call.');
            this.endCall();
        }
    }

    rejectCall() {
        if (this.state !== 'ringing' || !this.peer) return;
        socketService.sendCallSignal('webrtc_call_reject', {
            to: this.peer.username,
            call_id: this.callId,
        });
        this.cleanup();
    }

    // ── Signaling inbound ───────────────────────────────────────────────────────

    private async onAnswer(d: any) {
        if (d.call_id !== this.callId || !this.pc) return;
        try {
            await this.pc.setRemoteDescription(new RTCSessionDescription(d.sdp));
            this.remoteDescSet = true;
            await this.flushPendingCandidates();
            this.setState('in-call');
        } catch (e: any) {
            this.handlers.onError?.(e?.message || 'Call negotiation failed.');
            this.endCall();
        }
    }

    private async onRemoteIce(d: any) {
        if (d.call_id !== this.callId || !d.candidate) return;
        if (!this.pc || !this.remoteDescSet) {
            this.pendingCandidates.push(d.candidate);
            return;
        }
        try { await this.pc.addIceCandidate(new RTCIceCandidate(d.candidate)); } catch { /* ignore */ }
    }

    private onRejected(d: any) {
        if (d.call_id && d.call_id !== this.callId) return;
        this.handlers.onError?.('Call declined.');
        this.cleanup();
    }

    private onRemoteEnd(d: any) {
        if (d.call_id && d.call_id !== this.callId) return;
        this.cleanup();
    }

    private onUnavailable(d: any) {
        this.handlers.onError?.('User is offline or unavailable.');
        this.cleanup();
    }

    // ── Peer setup / teardown ────────────────────────────────────────────────────

    private async setupPeer(video: boolean) {
        this.localStream = await navigator.mediaDevices.getUserMedia({ audio: true, video });
        this.handlers.onLocalStream?.(this.localStream);

        this.pc = new RTCPeerConnection({ iceServers: ICE_SERVERS });
        this.remoteStream = new MediaStream();
        this.remoteDescSet = false;
        this.pendingCandidates = [];

        this.localStream.getTracks().forEach((t) => this.pc!.addTrack(t, this.localStream!));

        this.pc.ontrack = (ev) => {
            ev.streams[0]?.getTracks().forEach((t) => this.remoteStream!.addTrack(t));
            this.handlers.onRemoteStream?.(this.remoteStream);
        };
        this.pc.onicecandidate = (ev) => {
            if (ev.candidate && this.peer) {
                socketService.sendCallSignal('webrtc_ice', {
                    to: this.peer.username,
                    call_id: this.callId,
                    candidate: ev.candidate.toJSON(),
                });
            }
        };
        this.pc.onconnectionstatechange = () => {
            const st = this.pc?.connectionState;
            if (st === 'failed' || st === 'closed' || st === 'disconnected') {
                if (this.state === 'in-call' || this.state === 'connecting') this.cleanup();
            }
        };
    }

    private async flushPendingCandidates() {
        if (!this.pc) return;
        const pend = this.pendingCandidates;
        this.pendingCandidates = [];
        for (const c of pend) {
            try { await this.pc.addIceCandidate(new RTCIceCandidate(c)); } catch { /* ignore */ }
        }
    }

    // ── Controls ──────────────────────────────────────────────────────────────

    /** End an active or outgoing call, notifying the peer. */
    endCall() {
        if (this.peer && (this.state === 'calling' || this.state === 'connecting' || this.state === 'in-call')) {
            socketService.sendCallSignal('webrtc_call_end', {
                to: this.peer.username,
                call_id: this.callId,
            });
        }
        this.cleanup();
    }

    toggleMic(): boolean {
        const track = this.localStream?.getAudioTracks()[0];
        if (!track) return false;
        track.enabled = !track.enabled;
        return track.enabled;
    }

    toggleCam(): boolean {
        const track = this.localStream?.getVideoTracks()[0];
        if (!track) return false;
        track.enabled = !track.enabled;
        return track.enabled;
    }

    private cleanup() {
        try { this.pc?.close(); } catch { /* ignore */ }
        this.localStream?.getTracks().forEach((t) => t.stop());
        this.pc = null;
        this.localStream = null;
        this.remoteStream = null;
        this.pendingOffer = null;
        this.pendingCandidates = [];
        this.remoteDescSet = false;
        this.callId = '';
        this.peer = null;
        this.handlers.onLocalStream?.(null);
        this.handlers.onRemoteStream?.(null);
        this.setState('idle');
    }
}

export const webrtcCallService = new WebRTCCallService();
