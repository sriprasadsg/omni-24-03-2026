import React from 'react';

/** The article of a row the dialog edits (the parts the list already carries; the text is read from the server). */
export interface EditableArticle {
    id: string;
    title: string;
    tags: string[];
    starterKey?: string | null;
}

export interface ArticleEditDialogProps {
    mode: 'edit' | 'write';
    /** Edit: the article to change. */
    doc?: EditableArticle;
    /** Write: the title to start from (the question of a knowledge gap). */
    initialTitle?: string;
    /** Write: the knowledge-gap group this article answers; saving closes the gap. */
    gapGroupId?: string;
    onClose: () => void;
    /** Called once the article is saved, so the screen reads its list again. */
    onSaved: () => void;
}

/** Skeleton for the RED commit; the dialog is written in the next commit. */
export const ArticleEditDialog: React.FC<ArticleEditDialogProps> = () => null;
