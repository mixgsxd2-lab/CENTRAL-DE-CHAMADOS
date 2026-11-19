/* ==========================================================================
   Relatório em PDF dos Dashboards (Enfermagem e Hotelaria).

   1. `HRGRelatorioPDF.ligarBotao(...)` — no Dashboard: o botão discreto
      "PDF" (canto superior esquerdo) abre um pequeno painel com De / Até /
      Setor (andar) — e Serviço na Hotelaria — e "Gerar PDF" abre o
      relatório numa nova aba.
   2. `HRGRelatorioPDF.renderRelatorio(...)` — na página do relatório: busca
      as mesmas métricas do Dashboard, desenha cartões e gráficos com o
      mesmo sistema visual (dashboard_comum.js) e abre a janela de impressão
      do navegador já pronta para "Salvar como PDF" (A4).
   ========================================================================== */
window.HRGRelatorioPDF = (function () {
  "use strict";

  const escapeHtml = (t) => HRG.escapeHtml(t);

  // -----------------------------------------------------------------------
  // Botão + painel no Dashboard
  // -----------------------------------------------------------------------
  // opcoes: { botao, urlRelatorio, campos: [{ chave, rotulo, opcoes: [{valor, rotulo}] }] }
  function ligarBotao({ botao, urlRelatorio, campos = [] }) {
    if (!botao) return;
    const painel = document.createElement("div");
    painel.className = "painel-pdf";
    painel.hidden = true;
    painel.setAttribute("role", "dialog");
    painel.setAttribute("aria-label", "Gerar relatório em PDF");
    painel.innerHTML = `
      <div class="painel-pdf-titulo">Relatório em PDF</div>
      <div class="painel-pdf-datas">
        <div class="campo-filtro"><label for="pdfDataInicio">De</label><input type="date" id="pdfDataInicio"></div>
        <div class="campo-filtro"><label for="pdfDataFim">Até</label><input type="date" id="pdfDataFim"></div>
      </div>
      ${campos.map((c) => `
        <div class="campo-filtro">
          <label for="pdf_${c.chave}">${escapeHtml(c.rotulo)}</label>
          <select id="pdf_${c.chave}" data-chave="${c.chave}">
            <option value="">Todos</option>
            ${c.opcoes.map((o) => `<option value="${escapeHtml(o.valor)}">${escapeHtml(o.rotulo)}</option>`).join("")}
          </select>
        </div>`).join("")}
      <div class="painel-pdf-acoes">
        <button type="button" class="botao botao-fantasma pequeno" id="pdfCancelar">Cancelar</button>
        <button type="button" class="botao pequeno" id="pdfGerar">Gerar PDF</button>
      </div>
    `;
    botao.insertAdjacentElement("afterend", painel);
    botao.parentElement.classList.add("ancora-pdf");

    const inicio = painel.querySelector("#pdfDataInicio");
    const fim = painel.querySelector("#pdfDataFim");

    function abrir(abrirPainel) {
      painel.hidden = !abrirPainel;
      botao.setAttribute("aria-expanded", String(abrirPainel));
      if (abrirPainel) inicio.focus();
    }

    botao.setAttribute("aria-expanded", "false");
    botao.addEventListener("click", (e) => { e.stopPropagation(); abrir(painel.hidden); });
    painel.addEventListener("click", (e) => e.stopPropagation());
    document.addEventListener("click", () => { if (!painel.hidden) abrir(false); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !painel.hidden) { abrir(false); botao.focus(); } });
    painel.querySelector("#pdfCancelar").addEventListener("click", () => abrir(false));

    painel.querySelector("#pdfGerar").addEventListener("click", () => {
      if (inicio.value && fim.value && inicio.value > fim.value) {
        HRG.toast("A data inicial não pode ser depois da data final.", "erro");
        return;
      }
      const params = new URLSearchParams();
      if (inicio.value) params.set("data_inicio", inicio.value);
      if (fim.value) params.set("data_fim", fim.value);
      painel.querySelectorAll("select[data-chave]").forEach((s) => { if (s.value) params.set(s.dataset.chave, s.value); });
      window.open(`${urlRelatorio}?${params.toString()}`, "_blank", "noopener");
      abrir(false);
    });
  }

  // -----------------------------------------------------------------------
  // Página do relatório
  // -----------------------------------------------------------------------
  function dataBR(iso) {
    if (!iso) return "";
    const [a, m, d] = iso.split("-");
    return `${d}/${m}/${a}`;
  }

  function descricaoPeriodo(params) {
    const i = params.get("data_inicio"), f = params.get("data_fim");
    if (i && f) return `${dataBR(i)} a ${dataBR(f)}`;
    if (i) return `A partir de ${dataBR(i)}`;
    if (f) return `Até ${dataBR(f)}`;
    return "Todo o período";
  }

  // config: { urlMetricas, filtrosDescritos: [{ chave, rotulo, formatar? }], render(dados, D) }
  async function renderRelatorio(config) {
    const D = HRGDashboard;
    const params = new URLSearchParams(window.location.search);
    const api = new URLSearchParams();
    ["data_inicio", "data_fim", "andar", "servico"].forEach((k) => { if (params.get(k)) api.set(k, params.get(k)); });

    document.getElementById("relPeriodo").textContent = descricaoPeriodo(params);
    document.getElementById("relFiltros").innerHTML = config.filtrosDescritos.map((f) => {
      const v = params.get(f.chave);
      return `<span><b>${escapeHtml(f.rotulo)}:</b> ${escapeHtml(v ? (f.formatar ? f.formatar(v) : v) : "Todos")}</span>`;
    }).join("");
    document.getElementById("relGeradoEm").textContent = new Date().toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });

    const botaoImprimir = document.getElementById("botaoImprimir");
    botaoImprimir.addEventListener("click", () => window.print());

    try {
      const { dados } = await HRG.fetchJSON(`${config.urlMetricas}?${api.toString()}`);
      config.render(dados, D);
      document.body.classList.add("relatorio-pronto");
      // Dá tempo das fontes carregarem antes de abrir a impressão.
      const imprimir = () => setTimeout(() => window.print(), 300);
      if (document.fonts && document.fonts.ready) document.fonts.ready.then(imprimir); else imprimir();
    } catch (e) {
      document.getElementById("relConteudo").innerHTML = `<div class="vazio-dash">Não foi possível gerar o relatório. Tente novamente.</div>`;
    }
  }

  return { ligarBotao, renderRelatorio };
})();
