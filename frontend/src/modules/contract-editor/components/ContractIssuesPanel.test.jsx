import { render, screen } from "@testing-library/react";

import { ContractIssuesPanel } from "./ContractIssuesPanel";

describe("ContractIssuesPanel", () => {
  it("renders issue details, warning banner, auto-apply controls, and docx download button", () => {
    render(
      <ContractIssuesPanel
        warnings={[
          {
            code: "llm_insufficient_quota",
            message: "Показаны только локальные rule-based проверки",
          },
        ]}
        issues={[
          {
            paragraph_index: 2,
            fragment: "Заказчик",
            type: "TERM_MISUSE",
            severity: "high",
            confidence: "high",
            explanation: "Термин стороны используется непоследовательно",
            suggestion: "Унифицировать наименование стороны по всему договору",
            replacement: "Клиент",
          },
        ]}
        isDocx
        onApplyIssue={() => {}}
        onApplyAllSuggestions={() => {}}
        onDownloadMarked={() => {}}
        isDownloading={false}
      />,
    );

    expect(screen.getByText("Найденные замечания")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Показаны только локальные rule-based проверки",
    );
    expect(screen.getByText("Абзац #2")).toBeInTheDocument();
    expect(screen.getByText("Тип: TERM_MISUSE")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Применить все автозамены" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Применить замену" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Скачать размеченный DOCX" })).toBeInTheDocument();
  });
});
