/**
 * Every fixed UI label of the first-line service desk (Phase 85), in one module. Plain constants, no React.
 *
 * The texts are copied verbatim from 85-UI-SPEC.md (screens 2 to 6 and the Copywriting Contract); nothing is
 * reworded. The five strings in the first block are shared with the server: backend/service_desk/messages.py
 * holds the same five, and src/__tests__/serviceDeskCopy.test.ts reads that file and asserts they match.
 *
 * ACTV-08 scans this directory (shared/autonomous-ops-banned-terms.json): the feature is Autonomous Ops and
 * the desk is the Service desk; say withdraw, undo, hide. Keys are identifiers, not words shown to anyone.
 * Fields written {name} are filled by `fill`. Nothing here is rendered as HTML.
 */

// ---------------------------------------------------------------- shared with the server (D-13, D-22, D-24, D-25)

export const MARK = "AI-assisted answer from your IT knowledge base";
export const FOOTER = "Not right? Choose 'I still need help' and a person will take over.";
export const HANDOFF_NOTICE = "A person from IT will look at this.";
export const WITHDRAWN_NOTICE = "This answer was withdrawn; a person will follow up.";
export const OFFLINE_STATUS = "Offline: the local model isn't running";

/** Replace `{name}` fields. A field with no value is left as it is, so a half-filled text stays readable. */
export function fill(template: string, values: Record<string, string | number>): string {
    return template.replace(/\{(\w+)\}/g, (whole, name: string) =>
        Object.prototype.hasOwnProperty.call(values, name) ? String(values[name]) : whole);
}

// ---------------------------------------------------------------- 2. Service desk settings card

export const SETTINGS = {
    title: "Service desk",
    loadingHint: "Loading service desk settings",
    summaryOff: "Off",
    summaryOffScreens: "Off (screens not switched on)",
    summaryPosting: "Post answers (posting)",
    summaryPostingDrafts: "Post answers (drafts for now)",
    summaryDraftsOnly: "Drafts only",
    summaryRestoreNeeded: "Drafts only (restore needed)",
    modelOffline: "Local model offline",
    modelOnline: "Local model online",
    modelNotChecked: "Local model not checked",
    timeNotMeasured: "Answer time not measured",
    timeTypical: "Typical answer time {time}",
    extraWords: "{n} extra words",
    extraWord: "1 extra word",
    breakerTitle: ("The service desk dropped to Drafts only. 3 answers were withdrawn within 24 hours. "
        + "Answers stay drafts until someone restores Post answers."),
    breakerNote: "A requester choosing \"I still need help\" never counts toward this.",
    restoreButton: "Restore Post answers",
    restoreFirst: "Restore Post answers first.",
    chipOnline: "Online",
    chipOffline: "Offline",
    chipNotChecked: "Not checked",
    offlineDetail: ("Every ticket goes to a person and is marked \"service desk offline\" until it is back. "
        + "Ticket text never leaves this server."),
    onlineText: "The local model is running.",
    typicalTime: "Typical answer time: {time}",
    medianOf: "Median of the last {n} answers.",
    timeNotMeasuredYet: "Answer time not measured yet.",
    timeSafeDefaults: "Timeouts use safe defaults until an administrator measures this server.",
    queueLimit: ("An answer that isn't ready 10 minutes after the ticket arrives is dropped and the ticket "
        + "goes to a person."),
    modeGroupLabel: "Answers to requesters",
    modeHelper: ("Every organization starts at Drafts only. Only tickets a person raised get an answer, and "
        + "only from your own articles marked Help desk."),
    postingHelper: "Moving Autonomous Ops to Undoable-auto does not start posting answers. This switch does.",
    screensOff: ("The service desk is off because Tickets or Knowledge Base isn't switched on for this "
        + "organization. Ask a platform administrator."),
    save: "Save service desk settings",
    saving: "Saving...",
    discard: "Discard changes",
    tryAgain: "Try again",
} as const;

export const MODES = {
    off: {
        title: "Off",
        description: ("No answer is attempted and nothing is recorded. Tickets go to your team as they do "
            + "today. Drafts and answers already on tickets stay where they are."),
    },
    drafts: {
        title: "Drafts only",
        description: ("The service desk writes an answer from your Help desk articles and keeps it as a "
            + "draft. Your team decides whether to send it."),
    },
    post: {
        title: "Post answers",
        description: ("A qualifying answer is posted to the requester with the articles it cites. A person "
            + "can withdraw it with Undo."),
    },
} as const;

export const READINESS = {
    label: "Will answers be posted?",
    chipPosting: "Posting",
    chipDraftsForNow: "Drafts for now",
    level: {
        met: "Autonomous Ops is at Undoable-auto.",
        notMet: "Autonomous Ops is at {level}, so answers stay drafts. Only the level screen changes this.",
    },
    shadow: {
        met: "Shadow mode is lifted.",
        notMet: ("Shadow mode is on for this organization. The activity list shows what would have been "
            + "posted; answers stay drafts. Only a platform administrator lifts it."),
    },
    stop: {
        met: "Automatic actions are running.",
        notMet: "Automatic actions are stopped, so nothing is posted. Undo still works.",
    },
    hourlyLimit: {
        met: "Fewer than 20 answers posted in the last hour.",
        notMet: "20 answers were posted in the last hour. New answers are drafts until the hour passes.",
    },
    deskBreaker: {
        met: "No answers were withdrawn recently.",
        notMet: "The service desk dropped to Drafts only. Restore Post answers above.",
    },
} as const;

export const WORDS = {
    label: "Extra words that send a ticket to a person",
    helper: ("Built-in rules already send security, billing, legal, account-access and \"talk to a person\" "
        + "tickets to your team. Add your own words, for example payroll. A ticket containing any of them "
        + "goes to a person before the service desk reads it."),
    inputLabel: "Word or phrase",
    placeholder: "Word or phrase, for example payroll",
    add: "Add word",
    listLabel: "Extra words",
    remove: "Remove {word}",
    counter: "{n}/50 words",
    empty: "No extra words yet. The built-in rules still apply.",
    showRules: "Show built-in rules",
    hideRules: "Hide built-in rules",
    builtIn: [
        "Tickets of type security, and the Security Concern and Access Request tray templates.",
        ("Mentions of security, billing, legal or account access: unlocks, MFA resets, access grants, "
            + "permission changes and suspected compromise."),
        "Asking for a person.",
        "Tickets with critical priority.",
        ("Install Software and Hardware Request tickets go straight to a person; an article can't install "
            + "software or ship hardware."),
        "How-to questions about resetting your own password can be answered.",
    ],
} as const;

export const DIALOGS = {
    post: {
        title: "Post answers to requesters?",
        body: ("With Post answers on, a qualifying answer is shown to the person who raised the ticket, marked "
            + "\"AI-assisted answer from your IT knowledge base\", with the articles it cites. It posts only "
            + "while every condition in the list is met; otherwise it stays a draft. You can withdraw any "
            + "answer with Undo, and 3 withdrawals in 24 hours drop this back to Drafts only."),
        blocker: "Answers will stay drafts for now: {blocker}",
        keep: "Keep Drafts only",
        confirm: "Post answers",
        pending: "Saving...",
    },
    restore: {
        title: "Restore Post answers?",
        body: ("Answers will be posted again as soon as every condition is met. If 3 more answers are "
            + "withdrawn within 24 hours, the service desk drops to Drafts only again."),
        keep: "Keep Drafts only",
        confirm: "Restore Post answers",
        pending: "Restoring...",
    },
    discard: {
        title: "Discard this draft?",
        body: ("The requester never sees it. The service desk doesn't try again on this ticket, so a person "
            + "has to answer it."),
        keep: "Keep draft",
        confirm: "Discard draft",
        pending: "Discarding...",
    },
    starters: {
        title: "Add starter IT articles?",
        body: ("Adds {n} editable articles to your knowledge base, marked Help desk: password reset, VPN, "
            + "printer and the agent tray app. They are general, with placeholders such as \"your company's "
            + "VPN app\". Edit them to match your own setup before you rely on them. Adding them again adds "
            + "nothing twice."),
        keep: "Close without adding",
        confirm: "Add articles",
        pending: "Adding...",
    },
} as const;

// ---------------------------------------------------------------- 3. Staff draft panel and Reply to requester

export const DRAFT_PANEL = {
    title: "Draft answer",
    subtitle: "Written by the service desk {relative} from {n} articles. Only staff can see this.",
    chipDraft: "Draft",
    chipDraftWaiting: "Draft waiting",
    seenLabel: "What the requester will see",
    basedOn: "Based on",
    consequence: ("Sending shows this answer to {reporter} and moves the ticket to Waiting on customer. "
        + "There is no second AI attempt on this ticket."),
    sendAsIs: "Send as is",
    editAndSend: "Edit and send",
    discardDraft: "Discard draft",
    sending: "Sending...",
    editLabel: "Edit the answer",
    editHelper: ("Your edit is sent under the same AI-assisted label and cites the same articles. The cited "
        + "articles can't be changed here."),
    counter: "{n}/{max}",
    sendEdit: "Send edit",
    backToDraft: "Back to draft",
    unchanged: "Change the text, or use Send as is.",
    discardEdits: "Discard your edits?",
    discardEditsConfirm: "Discard edits",
    keepEditing: "Keep editing",
    resultSent: "Sent to {reporter} by {name} at {time}. The ticket is waiting on the customer.",
    resultDiscarded: "Draft discarded by {name} at {time}.",
    closedBlocked: "This ticket is {state}, so the draft can't be sent. You can still discard it.",
    personReplied: "A person already replied, so this draft can't be sent. You can still discard it.",
    alreadyHandled: "This draft was already handled.",
    noRequester: "This ticket has no requester who can see an answer, so the draft can't be sent.",
    sendFailed: "Couldn't send the answer: {message}. Try again.",
    sendFailedFallback: "Couldn't send the answer. Check your connection and try again.",
    discardFailed: "Couldn't discard the draft: {message}. Try again.",
    discardFailedFallback: "Couldn't discard the draft. Check your connection and try again.",
    draftReasons: {
        level_suggest: "Kept as a draft because Autonomous Ops is at Suggest.",
        shadow: "Kept as a draft because this organization is in shadow mode.",
        mode_drafts: "Kept as a draft because the service desk is set to Drafts only.",
        desk_rate_limit: "Kept as a draft because the hourly limit of 20 answers was reached.",
        stopped: "Kept as a draft because automatic actions are stopped.",
        desk_breaker: "Kept as a draft because the service desk dropped to Drafts only.",
        no_tray_window: "Kept as a draft because this computer's tray app can't show AI answers yet.",
        settings_unreadable: ("Kept as a draft because this organization's service desk settings couldn't "
            + "be read."),
    },
} as const;

export const REPLY_PICKER = {
    label: "Who can see this comment",
    staffOnly: "Staff only",
    replyToRequester: "Reply to requester",
    note: "{reporter} will see this reply in their ticket and get a notice. Don't include anything staff-only.",
    placeholder: "Write a reply to the requester...",
    sendLabel: "Send reply to requester",
    noTarget: "This ticket was raised by an automated source, so there is no requester to reply to.",
    chipSentToRequester: "Sent to requester",
    chipAiAssisted: "AI-assisted",
    chipDraft: "Draft",
    chipWithdrawn: "Withdrawn",
    sentBy: "Sent by {name}",
    postedAutomatically: "Posted automatically",
    withdrawnText: "This answer was withdrawn.",
    showOriginal: "Show original",
    listNote: "Comments are visible to staff only unless marked \"Sent to requester\".",
    statusWaiting: "Waiting on customer",
    sendFailed: "Couldn't send the reply: {message}. Try again.",
    sendFailedFallback: "Couldn't send the reply. Check your connection and try again.",
} as const;

// ---------------------------------------------------------------- 4. Requester answer panel

export const REQUESTER = {
    title: "Answer from IT support",
    basedOn: "Based on",
    returnClock: "If we don't hear back by {date}, a person from IT will pick this up.",
    replyAuthorFallback: "IT",
    fixed: "This fixed it",
    fixedHint: "Marks your ticket resolved.",
    saving: "Saving...",
    stillNeedHelp: "I still need help",
    noteLabel: "Tell IT what's still wrong (optional)",
    noteCounter: "{n}/1000",
    sendToIt: "Send to IT",
    sending: "Sending...",
    backToAnswer: "Back to answer",
    confirmed: "You confirmed this fixed it on {at}. The ticket is resolved.",
    helped: "Sent to IT. A person will take over.",
    handedOff: HANDOFF_NOTICE,
    withdrawn: WITHDRAWN_NOTICE,
    error: "Couldn't save your answer: {message}. Try again.",
    errorFallback: "Couldn't save your answer. Check your connection and try again.",
    noticeTitle: "Your ticket {number} has an answer",
} as const;

export const CITED = {
    loading: "Loading article...",
    readOnly: "Read-only. This is the article the answer was based on.",
    error: "Couldn't load this article. Try again.",
    gone: "This article is no longer available.",
    tryAgain: "Try again",
} as const;

// ---------------------------------------------------------------- 5. Activity rows and Undo

export const ACTIVITY = {
    openTicket: "Open ticket {number}",
    undo: "Undo",
    undoing: "Undoing...",
    undoAria: "Undo: Post ticket answer on {number}",
    undoHint: "Hides the answer from the requester and sends the ticket to a person.",
    undoToast: "Answer withdrawn. Ticket {number} went to a person.",
    undoToastBreaker: ("Answer withdrawn. 3 answers were withdrawn within 24 hours, so the service desk dropped "
        + "to Drafts only. A person with manage access can restore it."),
    undoFailed: "Couldn't undo this action: {message}. Try again.",
} as const;

// ---------------------------------------------------------------- 6. Knowledge Base screen

export const KB = {
    addStarters: "Add starter IT articles",
    startersAdded: "Starter IT articles added",
    readiness: "{k} articles are marked Help desk. The service desk cites only these.",
    readinessOne: "1 article is marked Help desk. The service desk cites only this one.",
    filterHelpDeskEmpty: "No articles are marked Help desk yet.",
    noHelpdeskArticles: ("The service desk has no Help desk articles to cite, so every ticket goes to a person. "
        + "Add the starter articles or mark your own articles as Help desk."),
    chipHelpDesk: "Help desk",
    chipStarterCopy: "Starter copy",
    chipPlatformReference: "Platform reference",
    switchLabel: "Help desk",
    switchAria: "Help desk: {title}",
    switchOn: "On",
    switchOff: "Off",
    editArticle: "Edit article",
    sharedReference: "Shared reference. Never used for ticket answers.",
    filterAll: "All Documents ({total})",
    filterHelpDesk: "Help desk ({k})",
    toggleOn: "\"{title}\" can now be cited in answers to requesters.",
    toggleOff: "\"{title}\" will no longer be cited in answers.",
    toggleFailed: "Couldn't change this article: {message}. Try again.",
    toggleFailedFallback: "Couldn't change this article. Check your connection and try again.",
    platformRefused: "The service desk isn't available for the platform organization.",
    starterFailed: "Couldn't add the starter articles: {message}. Try again.",
    starterFailedFallback: "Couldn't add the starter articles. Check your connection and try again.",
    articleDialogEdit: "Edit article",
    articleDialogWrite: "Write article",
    fieldTitle: "Title",
    fieldContent: "Content",
    fieldTags: "Tags",
    contentCounter: "{n}/{max}",
    helpdeskCheckbox: "Use this article for service desk answers (Help desk)",
    helpdeskHelper: ("When on, the service desk can quote this article to requesters. Don't put secrets, "
        + "passwords or internal-only notes in it."),
    starterCopyNote: ("This is a starter copy. Replace the general wording and placeholders with details for "
        + "your organization."),
    closeWithoutSaving: "Close without saving",
    saveArticle: "Save article",
    saving: "Saving...",
    saveFailed: "Couldn't save the article: {message}. Try again.",
    saveFailedFallback: "Couldn't save the article. Check your connection and try again.",
    articleLoading: "Loading article...",
    articleLoadFailed: "Couldn't load this article. Try again.",
    tryAgain: "Try again",
} as const;

export const GAPS = {
    tab: "Knowledge gaps ({n})",
    heading: "Knowledge gaps",
    intro: ("Questions from the last 90 days that the service desk couldn't answer because no Help desk "
        + "article matched. Links and email addresses are removed."),
    showDismissed: "Show dismissed ({d})",
    hideDismissed: "Hide dismissed",
    meta: "{n} tickets · Last asked {relative}",
    metaOne: "1 ticket · Last asked {relative}",
    showAllTickets: "Show all {n} tickets",
    writeArticle: "Write article",
    dismiss: "Dismiss gap",
    dismissing: "Dismissing...",
    restore: "Restore gap",
    showMore: "Show more gaps",
    otherLanguage: "{n} tickets were in another language and went to a person. The service desk answers in English only.",
    footnote: ("Software and hardware requests, and security, billing, legal or account-access tickets, are "
        + "not counted as gaps."),
    emptyHeading: "No knowledge gaps",
    emptyBody: ("Questions the service desk can't answer from your Help desk articles will show up here, "
        + "grouped by topic."),
    emptyOffHeading: "The service desk is off",
    emptyOffBody: ("Nothing is collected while it is off. Turn it on in Autonomous Ops, then questions that "
        + "need a new article show up here."),
    loadFailed: "Couldn't load knowledge gaps. Check your connection and try again.",
    tryAgain: "Try again",
    listLabel: "Knowledge gap groups",
    actionFailed: "Couldn't update this gap: {message}. Try again.",
    actionFailedFallback: "Couldn't update this gap. Check your connection and try again.",
} as const;

// ---------------------------------------------------------------- toasts, errors, validation (Copywriting Contract)

export const TOASTS = {
    settingsSaved: "Service desk settings saved.",
    modeSet: "Service desk set to {mode}.",
    restored: "Post answers restored. Answers post again once every condition is met.",
    draftDiscarded: "Draft discarded.",
    startersAdded: "Added {n} starter articles. Edit them to match your setup.",
    startersAddedOne: "Added 1 starter article. Edit it to match your setup.",
    startersNone: "Nothing to add. Your starter articles are already in your knowledge base.",
    articleSaved: "Article saved.",
    articleSavedGap: "Article saved and marked Help desk. The gap is closed.",
    gapDismissed: "Dismissed. It won't show here again unless you restore it.",
    noPermission: "You don't have permission to change these settings.",
} as const;

export const ERRORS = {
    settingsLoad: "Couldn't load service desk settings. Check your connection and try again.",
    settingsUnreadable: ("This organization's service desk settings couldn't be read, so answers are drafts "
        + "until they load."),
    settingsSave: "Couldn't save service desk settings: {message}. Try again.",
    settingsSaveFallback: "Couldn't save service desk settings. Check your connection and try again.",
} as const;

export const VALIDATION = {
    wordEmpty: "Enter a word or phrase.",
    wordShape: "Use 2 to 40 characters: letters, numbers, spaces and - ' & / .",
    wordDuplicate: "{word} is already on the list.",
    wordLimit: "You can add up to 50 words.",
    titleEmpty: "Enter a title.",
    contentEmpty: "Enter the article text.",
    contentTooLong: "The article is over {max} characters. Shorten it.",
    editUnchanged: "Change the text, or use Send as is.",
} as const;
