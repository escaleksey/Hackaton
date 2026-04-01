import { useState } from "react";

import { ContractEditor } from "../modules/contract-editor/components/ContractEditor";
import { ContractUploadForm } from "../modules/contract-editor/components/ContractUploadForm";
import { uploadContract, saveContract, downloadContract } from "../shared/api/contractsApi";
import { SectionCard } from "../shared/ui/SectionCard";

function triggerBrowserDownload(blob, fileName) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  link.click();
  URL.revokeObjectURL(url);
}

export function ContractWorkspacePage() {
  const [contract, setContract] = useState(null);
  const [correctedText, setCorrectedText] = useState("");
  const [correctedPages, setCorrectedPages] = useState([]);
  const [selectedPageIndex, setSelectedPageIndex] = useState(0);
  const [statusMessage, setStatusMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);

  const clearMessages = () => {
    setStatusMessage("");
    setErrorMessage("");
  };

  const syncDraftState = (draft) => {
    setContract(draft);
    setCorrectedText(draft.corrected_text);
    setCorrectedPages(draft.corrected_pages ?? []);
    setSelectedPageIndex(0);
  };

  const handleUpload = async ({ file, text }) => {
    setIsLoading(true);
    clearMessages();

    try {
      const draft = await uploadContract({ file, text });
      syncDraftState(draft);
      setStatusMessage(
        draft.source_format === "docx"
          ? `DOCX-договор загружен. Страниц в предпросмотре: ${draft.corrected_pages.length || 1}.`
          : "Договор загружен. Можно вносить правки и скачивать результат.",
      );
    } catch (error) {
      setErrorMessage(error.message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSave = async () => {
    if (!contract) {
      return;
    }

    setIsSaving(true);
    clearMessages();

    try {
      const updatedDraft = await saveContract(contract.id, {
        correctedText: contract.source_format === "docx" ? undefined : correctedText,
        correctedPages: contract.source_format === "docx" ? correctedPages : undefined,
      });
      setContract(updatedDraft);
      setCorrectedText(updatedDraft.corrected_text);
      setCorrectedPages(updatedDraft.corrected_pages ?? []);
      setStatusMessage("Правки сохранены на сервере.");
      return updatedDraft;
    } catch (error) {
      setErrorMessage(error.message);
      return null;
    } finally {
      setIsSaving(false);
    }
  };

  const handleSaveAndDownload = async () => {
    if (!contract) {
      return;
    }

    setIsDownloading(true);
    clearMessages();

    try {
      const updatedDraft = await saveContract(contract.id, {
        correctedText: contract.source_format === "docx" ? undefined : correctedText,
        correctedPages: contract.source_format === "docx" ? correctedPages : undefined,
      });
      setContract(updatedDraft);
      setCorrectedText(updatedDraft.corrected_text);
      setCorrectedPages(updatedDraft.corrected_pages ?? []);

      const { blob, fileName } = await downloadContract(contract.id);
      triggerBrowserDownload(blob, fileName);
      setStatusMessage("Исправленный договор сохранен и отправлен на скачивание.");
    } catch (error) {
      setErrorMessage(error.message);
    } finally {
      setIsDownloading(false);
    }
  };

  const handleDocxPageChange = (nextPage) => {
    setCorrectedPages((currentPages) =>
      currentPages.map((page, pageIndex) => {
        if (pageIndex !== selectedPageIndex) {
          return page;
        }

        return {
          ...page,
          ...nextPage,
        };
      }),
    );
  };

  return (
    <div className="page-shell">
      <div className="page">
        <header className="hero">
          <span className="hero__eyebrow">FastAPI + React</span>
          <h1>Сервис внесения исправлений в договор</h1>
          <p>
            MVP для второго этапа: загрузка `.txt` и `.docx`, редактирование договора в SPA и
            скачивание исправленной версии одним действием.
          </p>
        </header>

        <div className="workspace-grid">
          <div>
            <ContractUploadForm onSubmit={handleUpload} isLoading={isLoading} />

            <SectionCard
              title="Что уже умеет сервис"
              description="Теперь сервис поддерживает и обычный текст, и базовую работу с DOCX."
            >
              <ul>
                <li>загрузка `.txt` и `.docx`-договоров или вставка текста вручную;</li>
                <li>постраничный предпросмотр DOCX с сохранением базового форматирования;</li>
                <li>редактирование исправленной версии прямо в браузере;</li>
                <li>сохранение черновика на сервере;</li>
                <li>скачивание исправленного `.txt` или `.docx` в один клик.</li>
              </ul>
            </SectionCard>
          </div>

          <div>
            {statusMessage ? <div className="status status--info">{statusMessage}</div> : null}
            {errorMessage ? <div className="status status--error">{errorMessage}</div> : null}

            {contract ? (
              <ContractEditor
                contract={contract}
                correctedText={correctedText}
                correctedPages={correctedPages}
                selectedPageIndex={selectedPageIndex}
                onSelectedPageChange={setSelectedPageIndex}
                onCorrectedTextChange={setCorrectedText}
                onDocxPageTextChange={handleDocxPageChange}
                onSave={handleSave}
                onSaveAndDownload={handleSaveAndDownload}
                isSaving={isSaving}
                isDownloading={isDownloading}
              />
            ) : (
              <SectionCard
                title="Редактор пока пуст"
                description="После загрузки договора здесь появятся исходная и исправленная версии документа."
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
