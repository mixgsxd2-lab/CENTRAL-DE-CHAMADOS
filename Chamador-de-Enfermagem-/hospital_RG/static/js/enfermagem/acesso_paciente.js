/* ==========================================================================
   Expiração do acesso do paciente (QR Code do leito) — carregado nas telas
   do paciente (chamado e acompanhamento).

   O acesso vale até a meia-noite (horário de Fortaleza) ou até a Central
   clicar em "Expirar acesso"/"Expirar todos" (ver enfermagem/acesso.py).
   Esta tela consulta o servidor periodicamente e, assim que o acesso deixa
   de valer, troca todo o conteúdo pela tela "Acesso expirado" — sem o
   paciente precisar recarregar. O horário de corte vem sempre do servidor
   (`segundos_restantes`), nunca do relógio do celular.
   ========================================================================== */
(function () {
  "use strict";

  const INTERVALO_MS = 10000;
  let expirado = false;
  let temporizadorMeiaNoite = null;
  let polling = null;

  function mostrarExpirado() {
    if (expirado) return;
    expirado = true;
    if (polling) polling.parar();
    clearTimeout(temporizadorMeiaNoite);
    // Mesmo conteúdo de templates/enfermagem/acesso_expirado.html.
    document.title = "Acesso expirado — Hospital Rio Grande";
    document.body.className = "pagina-paciente";
    document.body.innerHTML = `
      <div class="tela-erro">
        <div class="tela-erro-caixa">
          <span class="tela-erro-codigo" aria-hidden="true">⏱</span>
          <h1 class="tela-erro-titulo">Acesso expirado</h1>
          <p>Escaneie o QR Code do seu leito para abrir um chamado.</p>
        </div>
      </div>
    `;
  }

  async function verificar() {
    if (expirado) return;
    let dados;
    try {
      const resp = await fetch("/api/enfermagem/acesso/status", { cache: "no-store" });
      if (!resp.ok) return;
      dados = await resp.json();
    } catch (e) {
      return; // sem rede: tenta de novo no próximo ciclo
    }
    if (!dados.valido) {
      mostrarExpirado();
      return;
    }
    // Agenda uma checagem logo depois da meia-noite, para a tela trocar na
    // hora mesmo que o próximo ciclo de polling ainda demore.
    clearTimeout(temporizadorMeiaNoite);
    if (dados.segundos_restantes < 6 * 3600) {
      temporizadorMeiaNoite = setTimeout(verificar, (dados.segundos_restantes + 1) * 1000);
    }
  }

  polling = HRG.pollWhileVisible(verificar, INTERVALO_MS);
  // Página restaurada do cache de "voltar/avançar" do navegador.
  window.addEventListener("pageshow", (ev) => { if (ev.persisted) verificar(); });

  // Outros scripts (ex.: envio de chamado recebendo 403 de acesso
  // expirado) podem forçar a tela na hora.
  window.HRGAcessoPaciente = { mostrarExpirado };
})();
