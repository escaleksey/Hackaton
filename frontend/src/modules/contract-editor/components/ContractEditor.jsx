import { DocumentPagePreview } from "./DocumentPagePreview";

export function ContractEditor({
  contract,
  correctedText,
  correctedPages,
  selectedPageIndex,
  onSelectedPageChange,
  onCorrectedTextChange,
  onDocxPageTextChange,
  onSave,
  onSaveAndDownload,
  isSaving,
  isDownloading,
}) {
  const isDocx = contract.source_format === "docx";
  const totalPages = isDocx
    ? Math.max(contract.original_pages?.length ?? 0, correctedPages?.length ?? 0, 1)
    : 0;
  const currentCorrectedPage = isDocx ? correctedPages?.[selectedPageIndex] : null;

  if (isDocx) {
    return (
      <section className="card editor editor--docx">
        <div>
          <h2>DOCX-редактор договора</h2>
        </div>

        <div className="editor__meta">
          <span>Файл: {contract.filename}</span>
          <span>Страниц: {totalPages}</span>
        </div>

        <div className="page-toolbar">
          <button
            className="button button--secondary"
            type="button"
            onClick={() => onSelectedPageChange(selectedPageIndex - 1)}
            disabled={selectedPageIndex === 0}
          >
            Предыдущая страница
          </button>
          <span className="page-toolbar__indicator">
            Страница {selectedPageIndex + 1} из {totalPages}
          </span>
          <button
            className="button button--secondary"
            type="button"
            onClick={() => onSelectedPageChange(selectedPageIndex + 1)}
            disabled={selectedPageIndex >= totalPages - 1}
          >
            Следующая страница
          </button>
        </div>

        <div className="document-columns document-columns--docx-single">
          <DocumentPagePreview
            title={`Редактирование · страница ${selectedPageIndex + 1}`}
            page={currentCorrectedPage}
            layout={contract.document_layout}
            editable
            onTextChange={onDocxPageTextChange}
            variant="editor"
          />
        </div>

        <div className="actions">
          <button className="button button--secondary" type="button" onClick={onSave} disabled={isSaving}>
            {isSaving ? "Сохраняем..." : "Сохранить правки"}
          </button>
          <button
            className="button button--primary"
            type="button"
            onClick={onSaveAndDownload}
            disabled={isSaving || isDownloading}
          >
            {isDownloading ? "Готовим файл..." : "Сохранить и скачать DOCX"}
          </button>
        </div>
      </section>
    );
  }

  return (
    <section className="card editor">
      <div>
        <h2>Редактор договора</h2>
        <p>Слева показан исходный текст, справа можно внести правки и сразу скачать итоговую версию.</p>
      </div>

      <div className="editor__meta">
        <span>Файл: {contract.filename}</span>
        <span>Черновик: {contract.id}</span>
      </div>

      <div className="editor__grid">
        <div className="editor__panel">
          <label htmlFor="contract-original">Исходный текст</label>
          <textarea id="contract-original" value={contract.original_text} readOnly />
        </div>

        <div className="editor__panel">
          <label htmlFor="contract-corrected">Исправленный текст</label>
          <textarea
            id="contract-corrected"
            value={correctedText}
            onChange={(event) => onCorrectedTextChange(event.target.value)}
          />
        </div>
      </div>

      <div className="actions">
        <button className="button button--secondary" type="button" onClick={onSave} disabled={isSaving}>
          {isSaving ? "Сохраняем..." : "Сохранить правки"}
        </button>
        <button
          className="button button--primary"
          type="button"
          onClick={onSaveAndDownload}
          disabled={isSaving || isDownloading}
        >
          {isDownloading ? "Готовим файл..." : "Сохранить и скачать"}
        </button>
      </div>
    </section>
  );
}
