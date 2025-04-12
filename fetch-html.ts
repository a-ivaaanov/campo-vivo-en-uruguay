import fetch from 'node-fetch';
import { JSDOM } from 'jsdom';
import * as fs from 'fs'; // ✅ правильный импорт для Node.js core-модуля

async function fetchHTMLText(url: string): Promise<string> {
  const response = await fetch(url);
  const html = await response.text();

  const dom = new JSDOM(html);
  const bodyText = dom.window.document.body.textContent || '';

  return bodyText.trim().replace(/\s+/g, ' ').slice(0, 30000);
}

// 🔗 URL целевой страницы MercadoLibre
const url = 'https://listado.mercadolibre.com.uy/inmuebles/terrenos/venta/';

fetchHTMLText(url).then(content => {
  const prompt = `# Анализ сайта: ${url}\n\n\`\`\`html\n${content}\n\`\`\``;

  console.log('\n--- Вставь это в Claude ---\n');
  console.log(prompt);

  fs.writeFileSync('output.txt', prompt); // 📄 сохранили в файл для удобства
});
