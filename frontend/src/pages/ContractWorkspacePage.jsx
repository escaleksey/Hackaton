import { useState } from "react";

import { ContractEditor } from "../modules/contract-editor/components/ContractEditor";
import { ContractIssuesPanel } from "../modules/contract-editor/components/ContractIssuesPanel";
import { ContractUploadForm } from "../modules/contract-editor/components/ContractUploadForm";
import { downloadContract, saveContract, uploadContract } from "../shared/api/contractsApi";
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
  const [issues, setIssues] = useState([]);
  const [warnings, setWarnings] = useState([]);
  const [selectedPageIndex, setSelectedPageIndex] = useState(0);
  const [statusMessage, setStatusMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);
  const [isMarkedDownloading, setIsMarkedDownloading] = useState(false);

  const clearMessages = () => {
    setStatusMessage("");
    setErrorMessage("");
  };

  const syncDraftState = (draft) => {
    setContract(draft);
    setCorrectedText(draft.corrected_text);
    setCorrectedPages(draft.corrected_pages ?? []);
    setIssues(draft.issues ?? []);
    setWarnings(draft.warnings ?? []);
    setSelectedPageIndex(0);
  };

  const handleUpload = async ({ file, text }) => {
    setIsLoading(true);
    clearMessages();

    try {
      const draft = await uploadContract({ file, text });
      syncDraftState(draft);
      setStatusMessage(`Документ проанализирован. Найдено замечаний: ${draft.issues?.length ?? 0}.`);
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
      syncDraftState(updatedDraft);
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
      syncDraftState(updatedDraft);

      const { blob, fileName } = await downloadContract(contract.id);
      triggerBrowserDownload(blob, fileName);
      setStatusMessage("Документ сохранен и отправлен на скачивание.");
    } catch (error) {
      setErrorMessage(error.message);
    } finally {
      setIsDownloading(false);
    }
  };

  const handleDownloadMarked = async () => {
    if (!contract) {
      return;
    }

    setIsMarkedDownloading(true);
    clearMessages();

    try {
      const { blob, fileName } = await downloadContract(contract.id);
      triggerBrowserDownload(blob, fileName);
      setStatusMessage("Размеченный документ отправлен на скачивание.");
    } catch (error) {
      setErrorMessage(error.message);
    } finally {
      setIsMarkedDownloading(false);
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
          <h1>Сервис анализа и разметки договоров</h1>
          <p>
            Загружайте `.docx` или `.txt`, получайте список замечаний в JSON и скачивайте документ с
            подсвеченными проблемными фрагментами.
          </p>
        </header>

        <div className="workspace-grid">
          <div>
            <ContractUploadForm onSubmit={handleUpload} isLoading={isLoading} />

            <SectionCard
              title="Что уже умеет сервис"
              description="В одном потоке сервис извлекает текст, анализирует договор и готовит размеченный результат."
            >
              <ul>
                <li>загрузка `.txt` и `.docx` договоров или вставка текста вручную;</li>
                <li>rule-based и LLM-анализ сроков, дат, ролей сторон и логики обязательств;</li>
                <li>строгий JSON со списком замечаний и уровнем критичности;</li>
                <li>подсветка проблемных фрагментов в DOCX и в браузерном превью;</li>
                <li>редактирование и повторное скачивание документа из интерфейса.</li>
              </ul>
            </SectionCard>
          </div>

          <div>
            {statusMessage ? <div className="status status--info">{statusMessage}</div> : null}
            {errorMessage ? <div className="status status--error">{errorMessage}</div> : null}

            {contract ? (
              <>
                <ContractIssuesPanel
                  issues={issues}
                  warnings={warnings}
                  isDocx={contract.source_format === "docx"}
                  onDownloadMarked={handleDownloadMarked}
                  isDownloading={isMarkedDownloading}
                />
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
              </>
            ) : (
              <SectionCard
                title="Редактор пока пуст"
                description="После загрузки договора здесь появятся замечания, разметка и редактируемая версия документа."
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
