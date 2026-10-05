/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { EditorContent } from "@tiptap/react";
import type { Editor } from "@tiptap/react";
import type { ReactNode } from "react";
// plane imports
import { ETextDirection } from "@plane/types";

type Props = {
  className?: string;
  children?: ReactNode;
  contentDirection?: ETextDirection;
  editor: Editor | null;
  id: string;
  tabIndex?: number;
};

export function EditorContentWrapper(props: Props) {
  const { editor, className, children, contentDirection = ETextDirection.RTL, tabIndex, id } = props;

  return (
    <div
      tabIndex={tabIndex}
      onFocus={() => editor?.chain().focus(undefined, { scrollIntoView: false }).run()}
      className={className}
      // Set on the content element rather than the editor container: the container also holds
      // the bubble menu, block menu and link previews, whose placement is computed from the
      // surrounding document direction. Tiptap renders each block without a `dir` of its own,
      // so this is what gives paragraphs their base direction.
      dir={contentDirection}
    >
      <EditorContent editor={editor} id={id} />
      {children}
    </div>
  );
}
