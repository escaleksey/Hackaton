const API_BASE = "/api/v1/contracts";

async function parseResponse(response) {
  if (!response.ok) {
    let message = "Ошибка при выполнении запроса.";

    try {
      const payload = await response.json();
      message = payload.detail ?? message;
    } catch (error) {
      message = response.statusText || message;
    }

    throw new Error(message);
  }

  return response;
}

export async function uploadContract({ file, text }) {
  const formData = new FormData();

  if (file) {
    formData.append("file", file);
  }

  if (text) {
    formData.append("text", text);
  }

  const response = await fetch(`${API_BASE}/upload`, {
    method: "POST",
    body: formData,
  });

  await parseResponse(response);
  return response.json();
}

export async function saveContract(contractId, { correctedText, correctedPages }) {
  const payload = correctedPages ? { corrected_pages: correctedPages } : { corrected_text: correctedText };

  const response = await fetch(`${API_BASE}/${contractId}/apply`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  await parseResponse(response);
  return response.json();
}

function extractFileName(disposition) {
  if (!disposition) {
    return null;
  }

  const utfMatch = disposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (utfMatch?.[1]) {
    return decodeURIComponent(utfMatch[1]);
  }

  const basicMatch = disposition.match(/filename="(.+?)"/i);
  return basicMatch?.[1] ?? null;
}

export async function downloadContract(contractId) {
  const response = await fetch(`${API_BASE}/${contractId}/download`);
  await parseResponse(response);

  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition");
  const fileName = extractFileName(disposition) ?? "contract_corrected.txt";

  return { blob, fileName };
}
