import { useEffect, useRef } from "react";

function makeRun(baseRun = {}, text = "") {
  return {
    text,
    bold: baseRun.bold ?? false,
    italic: baseRun.italic ?? false,
    underline: baseRun.underline ?? false,
    font_name: baseRun.font_name ?? null,
    font_size_pt: baseRun.font_size_pt ?? null,
    color: baseRun.color ?? null,
  };
}

function getParagraphStyle(block) {
  const firstRun = block.runs?.[0] ?? {};
  const fontSize = firstRun.font_size_pt ?? 12;
  const lineHeight = block.line_spacing && block.line_spacing > 5 ? `${block.line_spacing}pt` : undefined;

  return {
    textAlign: block.alignment ?? "left",
    marginTop: block.space_before_pt ? `${block.space_before_pt}pt` : "0pt",
    marginBottom: block.space_after_pt ? `${block.space_after_pt}pt` : "8pt",
    lineHeight,
    fontSize: `${fontSize}pt`,
  };
}

function getParagraphDataset(block, index) {
  return {
    "data-block-id": block.id ?? `page-block-${index + 1}`,
    "data-alignment": block.alignment ?? "left",
    "data-style-name": block.style_name ?? "",
    "data-space-before": block.space_before_pt ?? "",
    "data-space-after": block.space_after_pt ?? "",
    "data-line-spacing": block.line_spacing ?? "",
  };
}

function getRunDataset(run) {
  return {
    "data-bold": run.bold ? "true" : "false",
    "data-italic": run.italic ? "true" : "false",
    "data-underline": run.underline ? "true" : "false",
    "data-font-name": run.font_name ?? "",
    "data-font-size": run.font_size_pt ?? "",
    "data-color": run.color ?? "",
  };
}

function parseBoolean(value, fallback = false) {
  if (value == null || value === "") {
    return fallback;
  }

  return value === "true";
}

function parseNumber(value, fallback = null) {
  if (value == null || value === "") {
    return fallback;
  }

  const parsed = Number(value);
  return Number.isNaN(parsed) ? fallback : parsed;
}

function pxToPt(value) {
  if (!value) {
    return null;
  }

  const parsed = Number.parseFloat(value);
  if (Number.isNaN(parsed)) {
    return null;
  }

  return Number(parsed * 0.75);
}

function normalizeAlignment(value, fallback = "left") {
  if (!value) {
    return fallback;
  }

  if (["left", "center", "right", "justify"].includes(value)) {
    return value;
  }

  if (value === "start") {
    return "left";
  }

  if (value === "end") {
    return "right";
  }

  return fallback;
}

function rgbToHex(value, fallback = null) {
  if (!value) {
    return fallback;
  }

  if (value.startsWith("#")) {
    return value;
  }

  const match = value.match(/\d+/g);
  if (!match || match.length < 3) {
    return fallback;
  }

  return `#${match
    .slice(0, 3)
    .map((part) => Number(part).toString(16).padStart(2, "0"))
    .join("")}`;
}

function serializeTextNode(node, fallbackRun) {
  if (!node.textContent) {
    return [];
  }

  return [makeRun(fallbackRun, node.textContent)];
}

function serializeInlineNode(node, fallbackRun) {
  if (node.nodeType === Node.TEXT_NODE) {
    return serializeTextNode(node, fallbackRun);
  }

  if (node.nodeType !== Node.ELEMENT_NODE) {
    return [];
  }

  const element = node;
  const computedStyles = window.getComputedStyle(element);
  const nextRun = {
    ...fallbackRun,
    bold: parseBoolean(element.dataset.bold, fallbackRun.bold),
    italic: parseBoolean(element.dataset.italic, fallbackRun.italic),
    underline: parseBoolean(element.dataset.underline, fallbackRun.underline),
    font_name: element.dataset.fontName || computedStyles.fontFamily || fallbackRun.font_name,
    font_size_pt:
      parseNumber(element.dataset.fontSize, null) ??
      pxToPt(computedStyles.fontSize) ??
      fallbackRun.font_size_pt,
    color: element.dataset.color || rgbToHex(computedStyles.color, fallbackRun.color),
  };

  if (element.tagName === "STRONG" || element.tagName === "B") {
    nextRun.bold = true;
  }
  if (element.tagName === "EM" || element.tagName === "I") {
    nextRun.italic = true;
  }
  if (element.tagName === "U") {
    nextRun.underline = true;
  }
  if (element.tagName === "BR") {
    return [makeRun(nextRun, "\n")];
  }

  const childRuns = Array.from(element.childNodes).flatMap((childNode) =>
    serializeInlineNode(childNode, nextRun),
  );

  return childRuns.length ? childRuns : [makeRun(nextRun, "")];
}

function serializeParagraphElement(element, index, page) {
  const baseBlock = page?.blocks?.[index] ?? page?.blocks?.[index - 1] ?? page?.blocks?.[0];
  const baseRun = baseBlock?.runs?.[0] ?? {};
  const computedStyles = window.getComputedStyle(element);
  const childRuns = Array.from(element.childNodes).flatMap((childNode) =>
    serializeInlineNode(childNode, baseRun),
  );

  return {
    id: element.dataset.blockId || baseBlock?.id || `page-block-${index + 1}`,
    alignment: normalizeAlignment(
      element.dataset.alignment || computedStyles.textAlign,
      baseBlock?.alignment || "left",
    ),
    style_name: element.dataset.styleName || baseBlock?.style_name || null,
    space_before_pt:
      parseNumber(element.dataset.spaceBefore, null) ??
      pxToPt(computedStyles.marginTop) ??
      baseBlock?.space_before_pt,
    space_after_pt:
      parseNumber(element.dataset.spaceAfter, null) ??
      pxToPt(computedStyles.marginBottom) ??
      baseBlock?.space_after_pt,
    line_spacing:
      parseNumber(element.dataset.lineSpacing, null) ??
      pxToPt(computedStyles.lineHeight) ??
      baseBlock?.line_spacing,
    runs: childRuns.length ? childRuns : [makeRun(baseRun, "")],
  };
}

function serializePageFromEditor(root, page) {
  const paragraphElements = Array.from(root.children).filter(
    (child) => child.nodeType === Node.ELEMENT_NODE,
  );

  if (!paragraphElements.length) {
    return {
      ...page,
      blocks: [
        {
          id: page?.blocks?.[0]?.id ?? "page-block-1",
          alignment: page?.blocks?.[0]?.alignment ?? "left",
          style_name: page?.blocks?.[0]?.style_name ?? null,
          space_before_pt: page?.blocks?.[0]?.space_before_pt ?? null,
          space_after_pt: page?.blocks?.[0]?.space_after_pt ?? null,
          line_spacing: page?.blocks?.[0]?.line_spacing ?? null,
          runs: [makeRun(page?.blocks?.[0]?.runs?.[0], "")],
        },
      ],
    };
  }

  return {
    ...page,
    blocks: paragraphElements.map((element, index) => serializeParagraphElement(element, index, page)),
  };
}

function getRunStyle(run) {
  return {
    fontWeight: run.bold ? 700 : 400,
    fontStyle: run.italic ? "italic" : "normal",
    textDecoration: run.underline ? "underline" : "none",
    fontFamily: run.font_name ?? "Georgia, serif",
    fontSize: run.font_size_pt ? `${run.font_size_pt}pt` : undefined,
    color: run.color ?? "inherit",
  };
}

function applyStyles(target, styles) {
  Object.entries(styles).forEach(([key, value]) => {
    if (value !== undefined && value !== null) {
      target.style[key] = value;
    }
  });
}

function mountEditableContent(root, page) {
  root.replaceChildren();

  const blocks = page?.blocks?.length ? page.blocks : [{ id: "page-block-1", runs: [{ text: "" }] }];

  blocks.forEach((block, blockIndex) => {
    const paragraph = document.createElement("p");
    paragraph.className = "document-page__paragraph";
    applyStyles(paragraph, getParagraphStyle(block));

    Object.entries(getParagraphDataset(block, blockIndex)).forEach(([key, value]) => {
      if (value !== undefined && value !== null) {
        paragraph.setAttribute(key, String(value));
      }
    });

    const runs = block.runs?.length ? block.runs : [{ text: "" }];
    runs.forEach((run) => {
      const span = document.createElement("span");
      applyStyles(span, getRunStyle(run));

      Object.entries(getRunDataset(run)).forEach(([key, value]) => {
        if (value !== undefined && value !== null) {
          span.setAttribute(key, String(value));
        }
      });

      span.textContent = run.text || "";
      paragraph.appendChild(span);
    });

    root.appendChild(paragraph);
  });
}

export function DocumentPagePreview({
  title,
  page,
  layout,
  editable = false,
  onTextChange,
  variant = "preview",
}) {
  const width = layout?.page_width_pt ?? 595.3;
  const height = layout?.page_height_pt ?? 841.9;
  const pageRatio = width / height;
  const editorRef = useRef(null);

  useEffect(() => {
    if (!editable || !editorRef.current) {
      return;
    }

    if (editorRef.current.contains(document.activeElement)) {
      return;
    }

    mountEditableContent(editorRef.current, page);
  }, [editable, page]);

  return (
    <div className="document-preview">
      <div className="document-preview__header">{title}</div>
      <div className={`document-page-shell document-page-shell--${variant}`}>
        <div
          className={`document-page${editable ? " document-page--editable" : ""} document-page--${variant}`}
          style={{
            aspectRatio: `${width} / ${height}`,
            "--page-ratio": pageRatio,
          }}
        >
          {editable ? (
            <div
              className="document-page__editor"
              ref={editorRef}
              contentEditable
              suppressContentEditableWarning
              onInput={(event) => onTextChange?.(serializePageFromEditor(event.currentTarget, page))}
            />
          ) : page?.blocks?.length ? (
            page.blocks.map((block) => (
              <p className="document-page__paragraph" key={block.id} style={getParagraphStyle(block)}>
                {block.runs?.length
                  ? block.runs.map((run, index) => (
                      <span key={`${block.id}-${index}`} style={getRunStyle(run)}>
                        {run.text || ""}
                      </span>
                    ))
                  : " "}
              </p>
            ))
          ) : (
            <p className="document-page__empty">На этой странице пока нет содержимого.</p>
          )}
        </div>
      </div>
    </div>
  );
}
