import { useState } from "react";

export function ContractUploadForm({ onSubmit, isLoading }) {
  const [file, setFile] = useState(null);
  const [text, setText] = useState("");

  const handleSubmit = async (event) => {
    event.preventDefault();
    await onSubmit({ file, text });
  };

  return (
    <form className="card" onSubmit={handleSubmit}>
      <h2>Загрузка договора</h2>
      <p>Загрузите текстовый файл договора или вставьте текст вручную, чтобы сразу перейти к правкам</p>

      <div className="field">
        <label htmlFor="contract-file">Файл договора</label>
        <input
          id="contract-file"
          type="file"
          accept=".txt,.docx,text/plain,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
        />
      </div>

      <div className="actions">
        <button className="button button--primary" type="submit" disabled={isLoading}>
          {isLoading ? "Загружаем..." : "Открыть в редакторе"}
        </button>
      </div>
    </form>
  );
}
