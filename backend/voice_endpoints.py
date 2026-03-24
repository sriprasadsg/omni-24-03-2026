"""
Voice Bot Endpoints — Phase 8
Real speech-to-text and text-to-speech integration.
Supports Google Cloud Speech-to-Text and gTTS as fallback.
"""
import os
import io
import logging
import base64
from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional
from authentication_service import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/voice", tags=["Voice Bot"])


class TTSRequest(BaseModel):
    text: str
    language_code: str = "en-US"
    voice_name: Optional[str] = None
    speaking_rate: float = 1.0


class ChatVoiceRequest(BaseModel):
    transcript: str
    context: Optional[str] = "You are a helpful enterprise security assistant."


def transcribe_with_google(audio_bytes: bytes, language_code: str = "en-US") -> str:
    """Transcribe audio using Google Cloud Speech-to-Text."""
    try:
        from google.cloud import speech
        client = speech.SpeechClient()
        audio = speech.RecognitionAudio(content=audio_bytes)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.WEBM_OPUS,
            sample_rate_hertz=48000,
            language_code=language_code,
            enable_automatic_punctuation=True,
        )
        response = client.recognize(config=config, audio=audio)
        if response.results:
            return response.results[0].alternatives[0].transcript
        return ""
    except ImportError:
        raise Exception("google-cloud-speech not installed. Run: pip install google-cloud-speech")
    except Exception as e:
        raise Exception(f"Google STT error: {str(e)}")


def synthesize_speech_google(text: str, language_code: str = "en-US") -> bytes:
    """Convert text to speech using Google Cloud TTS."""
    try:
        from google.cloud import texttospeech
        client = texttospeech.TextToSpeechClient()
        synthesis_input = texttospeech.SynthesisInput(text=text)
        voice = texttospeech.VoiceSelectionParams(
            language_code=language_code,
            ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3
        )
        response = client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )
        return response.audio_content
    except ImportError:
        raise Exception("google-cloud-texttospeech not installed")
    except Exception as e:
        raise Exception(f"Google TTS error: {str(e)}")


def synthesize_speech_gtts(text: str, language: str = "en") -> bytes:
    """Fallback: use gTTS (no API key required)."""
    try:
        from gtts import gTTS
        tts = gTTS(text=text, lang=language)
        buffer = io.BytesIO()
        tts.write_to_fp(buffer)
        return buffer.getvalue()
    except ImportError:
        raise Exception("gTTS not installed. Run: pip install gTTS")


@router.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    language_code: str = "en-US",
    current_user=Depends(get_current_user)
):
    """
    Transcribe uploaded audio to text.
    Supports WebM, MP3, WAV formats.
    """
    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file")

    try:
        transcript = transcribe_with_google(audio_bytes, language_code)
        return {"transcript": transcript, "language": language_code, "provider": "google-speech"}
    except Exception as e:
        logger.warning(f"STT failed: {e}")
        # Return a helpful message if not configured
        return {
            "transcript": "",
            "error": str(e),
            "message": "Speech-to-text requires GOOGLE_APPLICATION_CREDENTIALS to be configured"
        }


@router.post("/synthesize")
async def synthesize_text(req: TTSRequest, current_user=Depends(get_current_user)):
    """
    Convert text to speech audio.
    Returns MP3 audio bytes as base64.
    """
    try:
        audio_bytes = synthesize_speech_google(req.text, req.language_code)
        audio_b64 = base64.b64encode(audio_bytes).decode()
        return {"audio_base64": audio_b64, "format": "mp3", "provider": "google-tts"}
    except Exception as google_err:
        logger.warning(f"Google TTS failed: {google_err}, trying gTTS")
        try:
            audio_bytes = synthesize_speech_gtts(req.text)
            audio_b64 = base64.b64encode(audio_bytes).decode()
            return {"audio_base64": audio_b64, "format": "mp3", "provider": "gtts"}
        except Exception as gtts_err:
            raise HTTPException(status_code=503, detail=f"TTS unavailable: {str(gtts_err)}")


@router.get("/status")
async def voice_status(current_user=Depends(get_current_user)):
    """Check voice service configuration status."""
    google_creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or os.getenv("GOOGLE_SPEECH_CREDENTIALS")
    return {
        "stt_provider": "google-cloud-speech" if google_creds else "not-configured",
        "tts_provider": "google-cloud-tts" if google_creds else "gtts-fallback",
        "configured": bool(google_creds),
        "note": "Set GOOGLE_APPLICATION_CREDENTIALS in .env to enable Google Cloud Speech services"
    }
