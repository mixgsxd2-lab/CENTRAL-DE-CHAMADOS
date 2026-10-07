/* ==========================================================================
   HRGDashboard — peças compartilhadas pelos Dashboards de Enfermagem e de
   Hotelaria: paleta de cores, cartões de resumo, gráficos de barras,
   gráfico "Chamados por período", gráfico empilhado "Chamados por andar",
   seletor de período e chips de filtros ativos.

   Antes cada dashboard tinha sua própria cópia dessas funções (e elas já
   tinham começado a divergir). Agora os dois usam exatamente o mesmo
   sistema — só mudam os dados e os rótulos. Carregado depois de common.js.
   ========================================================================== */
window.HRGDashboard = (function () {
  "use strict";

  const escapeHtml = HRG.escapeHtml;

  // Paleta lida dos tokens de base.css (--grafico-1 … --grafico-5), para
  // CSS e JS nunca divergirem.
  const estilos = getComputedStyle(document.documentElement);
  function token(nome, reserva) {
    const valor = estilos.getPropertyValue(nome).trim();
    return valor || reserva;
  }
  const PALETA = [
    token("--grafico-1", "#1b3a5c"),
    token("--grafico-2", "#2f5f8f"),
    token("--grafico-3", "#5c8fc4"),
    token("--grafico-4", "#8db5de"),
    token("--grafico-5", "#c2d8ee"),
  ];

  const vazioHtml = `<div class="vazio-dash">Sem dados ainda</div>`;

  function plural(n, singular, pluralTexto) {
    return `${n} ${n === 1 ? singular : pluralTexto}`;
  }

  function tendenciaHtml(comparativo) {
    if (!comparativo) return "";
    const delta = comparativo.delta_percentual;
    let classe = "tendencia-neutra", seta = "→";
    if (delta > 0) { classe = "tendencia-alta"; seta = "▲"; }
    else if (delta < 0) { classe = "tendencia-baixa"; seta = "▼"; }
    return `<span class="tendencia ${classe}" title="Comparado ao período anterior equivalente (${comparativo.total_anterior})">${seta} ${HRG.formatarPercentual(delta)}</span>`;
  }

  // cartoes: [{ rotulo, valor, destaque?, extra? }]
  function renderCartoes(container, cartoes) {
    container.innerHTML = cartoes.map((c) => `
      <div class="cartao-dash ${c.destaque ? "destaque" : ""}">
        <div class="rotulo-dash">${c.rotulo}</div>
        <div class="valor-dash">${c.valor}${c.extra || ""}</div>
      </div>
    `).join("");
  }

  // Barras horizontais simples. itens: [{ rotulo, valor, cor? }]
  function renderBarras(container, itens) {
    if (!itens.length || itens.every((i) => !i.valor)) { container.innerHTML = vazioHtml; return; }
    const max = Math.max(...itens.map((i) => i.valor), 1);
    const total = itens.reduce((s, i) => s + i.valor, 0);
    container.innerHTML = itens.map((i) => `
      <div class="barra-grafico-linha" title="${escapeHtml(i.rotulo)}: ${plural(i.valor, "chamado", "chamados")} (${total ? Math.round((i.valor / total) * 100) : 0}%)">
        <span class="rotulo-barra">${escapeHtml(i.rotulo)}</span>
        <div class="trilha-barra"><div class="preenchimento-barra" style="width:${(i.valor / max) * 100}%${i.cor ? `;background:${i.cor}` : ""}"></div></div>
        <span class="valor-barra">${i.valor}</span>
      </div>
    `).join("");
  }

  // Colunas do gráfico "Chamados por período". `serie` vem pronta do
  // backend (timeutils.serie_periodo): Hoje = últimas 24h por hora,
  // 7 dias = por dia, 30 dias = por semana, Tudo = por mês.
  function renderPeriodo(container, subtituloEl, serie) {
    const pontos = (serie && serie.pontos) || [];
    if (subtituloEl) subtituloEl.textContent = serie ? serie.descricao : "";
    if (!pontos.length || pontos.every((p) => p.total === 0)) { container.innerHTML = vazioHtml; return; }
    const max = Math.max(...pontos.map((p) => p.total), 1);
    const passoLegenda = pontos.length > 16 ? 3 : 1;
    container.innerHTML = `
      <div class="grafico-periodo ${pontos.length <= 8 ? "poucas-colunas" : ""}">
        ${pontos.map((p, i) => `
          <div class="coluna-periodo" title="${escapeHtml(p.detalhe)}: ${plural(p.total, "chamado", "chamados")}">
            ${p.total && pontos.length <= 31 ? `<span class="valor-coluna">${p.total}</span>` : ""}
            <div class="barra-vertical" style="height:${Math.max((p.total / max) * 100, p.total ? 4 : 1)}%"></div>
            <span class="legenda-periodo">${i % passoLegenda === 0 ? escapeHtml(p.rotulo) : "&nbsp;"}</span>
          </div>
        `).join("")}
      </div>
    `;
  }

  // Barras empilhadas por andar.
  // porAndar: { "1º Andar": { chave: n, ... } }; faixas: [{ chave, rotulo, cor, rodape? }]
  // destaque: chave da faixa citada no rodapé de cada andar (ex.: críticos);
  // `rodape: [singular, plural]` dessa faixa dá o texto (ex.: "crítico(s)").
  function renderEmpilhado(container, porAndar, faixas, destaque) {
    const entradas = Object.entries(porAndar || {});
    const totais = entradas.map(([, f]) => faixas.reduce((s, fx) => s + (f[fx.chave] || 0), 0));
    if (!entradas.length || totais.every((t) => t === 0)) { container.innerHTML = vazioHtml; return; }
    const max = Math.max(...totais, 1);
    const somaGeral = totais.reduce((s, t) => s + t, 0);
    container.innerHTML = entradas.map(([andar, f], i) => {
      const total = totais[i];
      const segmentos = faixas.map((fx) => (f[fx.chave]
        ? `<i style="width:${(f[fx.chave] / max) * 100}%;background:${fx.cor}" title="${escapeHtml(fx.rotulo)}: ${f[fx.chave]}"></i>`
        : "")).join("");
      const detalhe = faixas.map((fx) => `${fx.rotulo} ${f[fx.chave] || 0}`).join(", ");
      const fxDestaque = faixas.find((fx) => fx.chave === destaque);
      const rotuloAndar = andar.replace(/\s*—\s*LEITOS\s*$/i, "");
      return `
        <div class="barra-grafico-linha" title="${escapeHtml(rotuloAndar)}: ${total} chamados (${escapeHtml(detalhe)})">
          <span class="rotulo-barra">${escapeHtml(rotuloAndar)}</span>
          <div class="trilha-barra empilhada">${segmentos}</div>
          <span class="valor-barra">${total}</span>
        </div>
        <div class="andar-total">${somaGeral ? Math.round((total / somaGeral) * 100) : 0}% do total${fxDestaque ? ` · ${escapeHtml(plural(f[destaque] || 0, ...(fxDestaque.rodape || [fxDestaque.rotulo.toLowerCase(), fxDestaque.rotulo.toLowerCase()])))}` : ""}</div>
      `;
    }).join("");
  }

  function legendaHtml(faixas) {
    return faixas.map((fx) => `<span><i style="background:${fx.cor}"></i>${escapeHtml(fx.rotulo)}</span>`).join("");
  }

  // Seletor Hoje | 7 dias | 30 dias | Tudo. Devolve `marcar(valor)`.
  function ligarSeletorPeriodo(elemento, aoMudar) {
    function marcar(valor) {
      elemento.querySelectorAll("button").forEach((b) => b.classList.toggle("ativo", b.dataset.periodo === (valor || "")));
    }
    elemento.querySelectorAll("button").forEach((botao) => {
      botao.addEventListener("click", () => {
        marcar(botao.dataset.periodo);
        aoMudar(botao.dataset.periodo || "");
      });
    });
    return { marcar };
  }

  function ligarPainelFiltros(botao, painel) {
    if (!botao || !painel) return;
    botao.addEventListener("click", () => {
      const abrir = painel.hidden;
      painel.hidden = !abrir;
      botao.setAttribute("aria-expanded", String(abrir));
    });
  }

  // Chips "filtro ativo ✕". definicoes: [{ chave, el, rotulo(valor), ignorar? }]
  function renderFiltrosAtivos(container, definicoes, aoRemover) {
    const ativos = definicoes.filter((d) => d.el.value && d.el.value !== d.ignorar);
    if (!ativos.length) { container.innerHTML = ""; return; }
    container.innerHTML = ativos.map((d) => `
      <span class="filtro-ativo-chip" data-chave="${d.chave}">${escapeHtml(d.rotulo(d.el.value))}<button type="button" aria-label="Remover filtro">✕</button></span>
    `).join("");
    container.querySelectorAll(".filtro-ativo-chip button").forEach((botao) => {
      botao.addEventListener("click", () => {
        const def = definicoes.find((d) => d.chave === botao.parentElement.dataset.chave);
        if (def) { def.el.value = def.ignorar || ""; aoRemover(def.chave); }
      });
    });
  }

  return {
    PALETA, tendenciaHtml, renderCartoes, renderBarras, renderPeriodo, renderEmpilhado,
    legendaHtml, ligarSeletorPeriodo, ligarPainelFiltros, renderFiltrosAtivos,
  };
})();
