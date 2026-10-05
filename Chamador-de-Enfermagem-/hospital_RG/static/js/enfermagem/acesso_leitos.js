/* ==========================================================================
   Configurações → "Acesso pelo QR Code".

   Lista os leitos por andar, mostra quais foram liberados hoje (alguém
   escaneou o QR Code e o acesso ainda vale) e permite expirar o acesso de
   um leito ou de todos — sempre com confirmação — e um cronômetro de
   quanto falta para o reset da meia-noite. A regra em si vive no
   backend (enfermagem/acesso.py); o celular do paciente percebe a
   revogação sozinho em poucos segundos (static/js/enfermagem/acesso_paciente.js).
   ========================================================================== */
(function () {
  "use strict";

  const escapeHtml = HRG.escapeHtml;

  const cronometro = document.getElementById("cronometroReset");
  const lista = document.getElementById("listaAcessoLeitos");
  const busca = document.getElementById("buscaLeitoAcesso");
  const totalLiberados = document.getElementById("totalLiberados");
  const botaoExpirarTodos = document.getElementById("botaoExpirarTodos");

  const fundoModal = document.getElementById("fundoModalExpirar");
  const textoModal = document.getElementById("textoModalExpirar");
  const botaoConfirmar = document.getElementById("botaoConfirmarExpirar");

  let andares = [];
  // Instante (relógio deste navegador) em que ocorre o reset — recalculado
  // a cada carga a partir de `segundos_ate_reset`, que vem do servidor
  // (horário de Fortaleza), então um relógio errado no PC não atrapalha.
  let resetEm = null;
  let acaoPendente = null; // { andar, leito } ou { todos: true }

  function render() {
    const termo = (busca.value || "").trim().toLowerCase();
    let liberados = 0;
    andares.forEach((a) => a.leitos.forEach((l) => { if (l.liberado_desde) liberados++; }));
    totalLiberados.textContent = liberados;

    const grupos = andares
      .map((a) => ({
        ...a,
        filtrados: termo
          ? a.leitos.filter((l) => l.leito.toLowerCase().includes(termo) || a.andar_label.toLowerCase().includes(termo))
          : a.leitos,
      }))
      .filter((a) => a.filtrados.length);

    if (!grupos.length) {
      lista.innerHTML = `<p class="texto-carregando">Nenhum leito encontrado.</p>`;
      return;
    }

    lista.innerHTML = grupos.map((a) => `
      <div class="grupo-andar-config">
        <h3>${escapeHtml(a.andar_label)}</h3>
        <div class="grade-leitos-acesso">
          ${a.filtrados.map((l) => `
            <div class="leito-acesso ${l.liberado_desde ? "liberado" : ""} ${l.ativo ? "" : "inativo"}">
              <span class="leito-acesso-numero">${escapeHtml(l.leito)}</span>
              <span class="leito-acesso-status">${
                !l.ativo ? "Leito desativado"
                  : l.liberado_desde ? `Liberado às ${escapeHtml(l.liberado_desde)}` : "Sem acesso hoje"
              }</span>
              <button type="button" class="botao botao-fantasma pequeno botao-expirar-leito"
                data-andar="${escapeHtml(a.andar)}" data-leito="${escapeHtml(l.leito)}">Expirar acesso</button>
            </div>
          `).join("")}
        </div>
      </div>
    `).join("");
  }

  async function carregar() {
    try {
      const { dados } = await HRG.fetchJSON("/api/enfermagem/acesso/leitos");
      andares = dados.andares;
      resetEm = Date.now() + dados.segundos_ate_reset * 1000;
      atualizarCronometro();
      render();
    } catch (e) {
      if (!andares.length) lista.innerHTML = `<p class="texto-carregando">Não foi possível carregar os leitos.</p>`;
    }
  }

  function atualizarCronometro() {
    if (resetEm == null) return;
    const restante = Math.max(0, Math.round((resetEm - Date.now()) / 1000));
    const h = String(Math.floor(restante / 3600)).padStart(2, "0");
    const m = String(Math.floor((restante % 3600) / 60)).padStart(2, "0");
    const s = String(restante % 60).padStart(2, "0");
    cronometro.textContent = `${h}:${m}:${s}`;
    if (restante === 0) {
      // Meia-noite: busca de novo (zera os "liberados hoje" e o cronômetro
      // volta para 24:00:00).
      resetEm = null;
      setTimeout(carregar, 1500);
    }
  }

  setInterval(atualizarCronometro, 1000);
  HRG.pollWhileVisible(carregar, 15000);

  busca.addEventListener("input", render);

  // ---------------------------------------------------------------------
  // Confirmação ("Tem certeza?")
  // ---------------------------------------------------------------------
  function abrirConfirmacao(acao) {
    acaoPendente = acao;
    textoModal.textContent = acao.todos
      ? "O acesso de TODOS os leitos será expirado agora. Quem estiver com a tela aberta no celular perde o acesso na hora e precisará escanear o QR Code do leito de novo."
      : `O acesso do leito ${acao.leito} será expirado agora. Quem estiver com a tela aberta no celular perde o acesso na hora e precisará escanear o QR Code do leito de novo.`;
    fundoModal.classList.add("aberto");
    botaoConfirmar.focus();
  }

  function fecharConfirmacao() {
    fundoModal.classList.remove("aberto");
    acaoPendente = null;
  }

  lista.addEventListener("click", (ev) => {
    const botao = ev.target.closest(".botao-expirar-leito");
    if (botao) abrirConfirmacao({ andar: botao.dataset.andar, leito: botao.dataset.leito });
  });
  botaoExpirarTodos.addEventListener("click", () => abrirConfirmacao({ todos: true }));

  document.getElementById("botaoFecharModalExpirar").addEventListener("click", fecharConfirmacao);
  document.getElementById("botaoCancelarExpirar").addEventListener("click", fecharConfirmacao);
  fundoModal.addEventListener("click", (ev) => { if (ev.target === fundoModal) fecharConfirmacao(); });
  HRG.fecharComEsc(() => fundoModal.classList.contains("aberto"), fecharConfirmacao);

  botaoConfirmar.addEventListener("click", () =>
    HRG.comBotaoTravado(botaoConfirmar, async () => {
      const acao = acaoPendente;
      if (!acao) return;
      try {
        if (acao.todos) {
          await HRG.fetchJSON("/api/enfermagem/acesso/expirar-todos", { method: "POST" });
          HRG.toast("Acesso de todos os leitos expirado.", "sucesso");
        } else {
          await HRG.fetchJSON("/api/enfermagem/acesso/expirar", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ andar: acao.andar, leito: acao.leito }),
          });
          HRG.toast(`Acesso do leito ${acao.leito} expirado.`, "sucesso");
        }
        fecharConfirmacao();
        carregar();
      } catch (e) {
        HRG.toast(e.message || "Não foi possível expirar o acesso.", "erro");
      }
    })
  );
})();
