import { render, screen } from "@testing-library/react";

import { ContractEditor } from "./ContractEditor";

const docxContract = {
  id: "draft-1",
  filename: "contract.docx",
  source_format: "docx",
  document_layout: {
    page_width_pt: 595.3,
    page_height_pt: 841.9,
  },
  original_pages: [
    {
      number: 1,
      blocks: [
        {
          id: "block-1",
          alignment: "center",
          style_name: "Heading 1",
          space_before_pt: 0,
          space_after_pt: 12,
          line_spacing: 18,
          runs: [{ text: "Заголовок", bold: true, font_size_pt: 16 }],
        },
      ],
    },
  ],
};

describe("ContractEditor", () => {
  it("renders a single editable DOCX page without original preview", () => {
    render(
      <ContractEditor
        contract={docxContract}
        correctedText=""
        correctedPages={docxContract.original_pages}
        selectedPageIndex={0}
        onSelectedPageChange={() => {}}
        onCorrectedTextChange={() => {}}
        onDocxPageTextChange={() => {}}
        onSave={() => {}}
        onSaveAndDownload={() => {}}
        isSaving={false}
        isDownloading={false}
      />,
    );

    expect(screen.getByText("DOCX-редактор договора")).toBeInTheDocument();
    expect(screen.getByText("Редактирование · страница 1")).toBeInTheDocument();
    expect(screen.queryByText("Оригинал · страница 1")).not.toBeInTheDocument();
    expect(screen.getByText("Страница 1 из 1")).toBeInTheDocument();
  });
});
