// ======= Filtros =======
const filtroAno = document.getElementById("filtroAno");
const filtroMes = document.getElementById("filtroMes");
const filtroCid = document.getElementById("filtroCid");
const btnLimpar  = document.getElementById("btnLimpar");

// FABs (fixos, definidos no base.html)
// Fallback: se ainda existirem os antigos, também funcionam.
const btnExport      = document.getElementById("btnExport")      || document.getElementById("btnExportMobile");
const btnToggleTheme = document.getElementById("btnToggleTheme") || document.getElementById("btnToggleThemeMobile");

// ======= KPIs =======
const kpiInternacoes = document.getElementById("kpiInternacoes");
const kpiMediaDias   = document.getElementById("kpiMediaDias");
const kpiObitos      = document.getElementById("kpiObitos");
const kpiValor       = document.getElementById("kpiValor");

// ======= Paleta =======
const colors = {
  azul: "#0ea5e9",
  rosa: "#ec4899",
  roxo: "#6366f1",
  verde: "#22c55e",
  laranja: "#f97316",
  vermelho: "#ef4444",
  cinza: "#94a3b8"
};

function formatNumberBR(n) {
  if (n === null || n === undefined || isNaN(n)) return "–";
  return Number(n).toLocaleString("pt-BR");
}

function setKpi(el, value) {
  const txt = value ?? "–";
  if (!el) return;
  el.textContent = txt;
  el.setAttribute("title", txt);
}

// Ajuste inteligente de fonte do KPI (só reduz quando necessário)
function smartFitKpi(el) {
  if (!el) return;
  el.style.fontSize = "";
  el.style.whiteSpace = "nowrap";

  const container = el.parentElement;
  const available = container ? container.clientWidth : el.clientWidth;
  const isMobileOrNarrow = window.innerWidth < 576 || available < 220;

  if (isMobileOrNarrow) {
    fitKpiToWidth(el, 24, 11, 1);
  } else {
    if (el.scrollWidth > available) {
      fitKpiToWidth(el, 28, 16, 1);
    }
  }
}

function fitKpiToWidth(el, maxPx = 26, minPx = 9, step = 1) {
  if (!el) return;
  el.style.whiteSpace = "nowrap";
  el.style.fontSize = maxPx + "px";
  const available = (el.parentElement?.clientWidth || el.clientWidth) - 2;
  let fs = maxPx;
  while (el.scrollWidth > available && fs > minPx) {
    fs -= step;
    el.style.fontSize = fs + "px";
  }
  if (window.innerWidth < 576 && el.scrollWidth > available) {
    el.style.whiteSpace = "normal";
  }
}

// ======= Plotly base =======
function getBaseLayout() {
  const isDark = document.body.classList.contains("theme-dark");
  return {
    paper_bgcolor: "transparent",
    plot_bgcolor: "transparent",
    font: { color: isDark ? "#f1f5f9" : "#1e293b", family: "Inter, sans-serif" },
    margin: { t: 44, r: 20, b: 50, l: 70 },
    hoverlabel: {
      bgcolor: isDark ? "#0f172a" : "#ffffff",
      bordercolor: isDark ? "#334155" : "#e2e8f0",
      font: { color: isDark ? "#f1f5f9" : "#1e293b" }
    }
  };
}

const plotConfig = {
  responsive: true,
  displaylogo: false,
  modeBarButtonsToRemove: [
    "toImage","lasso2d","select2d","zoomIn2d","zoomOut2d","autoScale2d",
    "toggleSpikelines","hoverClosestCartesian","hoverCompareCartesian"
  ]
};

// ======= Fetch + Render =======
function fetchDashboard() {
  const ano = filtroAno?.value || "";
  const mes = filtroMes?.value || "";
  const cid = filtroCid?.value || "";

  const params = new URLSearchParams();
  if (ano) params.set("ano", ano);
  if (mes) params.set("mes", mes);
  if (cid) params.set("cid", cid);

  const url = "/api/dashboard" + (params.toString() ? `?${params.toString()}` : "");

  fetch(url)
    .then(r => r.json())
    .then(res => {
      // KPIs
      setKpi(kpiInternacoes, formatNumberBR(res.kpis.total_internacoes));
      setKpi(kpiMediaDias,   formatNumberBR(res.kpis.media_dias));
      setKpi(kpiObitos,      formatNumberBR(res.kpis.total_obitos));
      setKpi(kpiValor,       "R$ " + formatNumberBR(res.kpis.valor_total));
      smartFitKpi(kpiValor);

      const baseLayout = getBaseLayout();

      // Internações por Ano
      const gy = res.series.by_year || [];
      const anos = gy.map(d => String(d.ANO_CMPT));
      const anosUnicos = [...new Set(anos)];

      Plotly.newPlot("grafByYear", [{
        x: anos,
        y: gy.map(d => d.internacoes),
        type: "bar",
        marker: { color: colors.azul },
        hovertemplate: "Ano %{x}<br><b>%{y}</b> internações<extra></extra>"
      }], {
        ...baseLayout,
        title: { text: "Internações por Ano", x: 0, font: { size: 16 } },
        xaxis: { title: "Ano", type: "category", categoryorder: "array", categoryarray: anosUnicos },
        yaxis: { title: "Internações", rangemode: "tozero", tickformat: "d" }
      }, plotConfig);

      // Distribuição Mensal
      const gm = res.series.by_month || [];
      const grafByMonthDiv = document.getElementById("grafByMonth");
      const meses = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"];

      if (ano && gm.length > 0) {
        grafByMonthDiv.innerHTML = "";
        const xMes = gm.map(d => d.MES_NOME);
        const yVals = gm.map(d => d.internacoes);
        const nonZero = yVals.filter(v => (v || 0) > 0).length;

        const trace = (nonZero <= 1)
          ? { x: xMes, y: yVals, type: "bar", marker: { color: colors.laranja },
              hovertemplate: "%{x}<br><b>%{y}</b> internações<extra></extra>" }
          : { x: xMes, y: yVals, type: "scatter", mode: "lines+markers",
              line: { shape: "spline", color: colors.laranja, width: 3 },
              marker: { size: 8 },
              hovertemplate: "%{x}<br><b>%{y}</b> internações<extra></extra>" };

        Plotly.newPlot("grafByMonth", [trace], {
          ...baseLayout,
          title: { text: `Internações Mensais (${ano})`, x: 0, font: { size: 16 } },
          xaxis: { title: "Mês", type: "category", categoryorder: "array", categoryarray: meses },
          yaxis: { title: "Internações", rangemode: "tozero", tickformat: "d" }
        }, plotConfig);

      } else {
        grafByMonthDiv.innerHTML =
          "<div class='text-secondary small'>Selecione um <b>ano</b> para ver a distribuição mensal.</div>";
      }

      // Sexo
      const gs = res.breakdowns.by_sex || [];
      const sexColors = gs.map(d => {
        if (d.SEXO === "Masculino") return colors.azul;
        if (d.SEXO === "Feminino") return colors.rosa;
        return colors.cinza;
      });

      Plotly.newPlot("grafSex", [{
        labels: gs.map(d => d.SEXO),
        values: gs.map(d => d.internacoes),
        type: "pie",
        hole: 0.45,
        marker: { colors: sexColors },
        hovertemplate: "%{label}<br><b>%{value}</b> internações<extra></extra>"
      }], {
        ...baseLayout,
        title: { text: "Distribuição por Sexo", x: 0, font: { size: 16 } },
        showlegend: true,
        legend: { orientation: "h", y: -0.2 }
      }, plotConfig);

      // Faixa Etária
      const ga = res.breakdowns.by_age || [];
      Plotly.newPlot("grafAge", [{
        x: ga.map(d => d.FAIXA_IDADE),
        y: ga.map(d => d.internacoes),
        type: "bar",
        marker: { color: colors.roxo },
        hovertemplate: "Faixa %{x}<br><b>%{y}</b> internações<extra></extra>"
      }], {
        ...baseLayout,
        title: { text: "Internações por Faixa Etária", x: 0, font: { size: 16 } },
        xaxis: { title: "Faixa etária", type: "category" },
        yaxis: { title: "Internações", rangemode: "tozero", tickformat: "d" }
      }, plotConfig);

      // Top 10 CIDs
      const gcid = res.breakdowns.by_cid_top || [];
      Plotly.newPlot("grafCidTop", [{
        x: gcid.map(d => d.internacoes),
        y: gcid.map(d => d.CID3),
        type: "bar",
        orientation: "h",
        marker: { color: colors.verde },
        customdata: gcid.map(d => d.Descricao),
        hovertemplate: "CID %{y}<br>%{customdata}<br><b>%{x}</b> internações<extra></extra>"
      }], {
        ...baseLayout,
        title: { text: "Top 10 Diagnósticos (CID-10)", x: 0, font: { size: 16 } },
        xaxis: { title: "Internações", rangemode: "tozero", tickformat: "d" },
        yaxis: { title: "CID", type: "category" }
      }, plotConfig);

      // Tabela CIDs
      const tabelaDiv = document.getElementById("tabelaCidTop");
      if (gcid.length > 0) {
        const isDark = document.body.classList.contains("theme-dark");
        let html = `
          <div class="table-responsive">
            <table class="table table-sm ${isDark ? "table-dark" : "table-light"} table-striped align-middle">
              <thead>
                <tr>
                  <th scope="col">CID</th>
                  <th scope="col">Descrição</th>
                  <th scope="col">Internações</th>
                </tr>
              </thead>
              <tbody>
        `;
        gcid.forEach(row => {
          html += `
            <tr>
              <td><span class="badge bg-success">${row.CID3}</span></td>
              <td>${row.Descricao}</td>
              <td>${formatNumberBR(row.internacoes)}</td>
            </tr>
          `;
        });
        html += "</tbody></table></div>";
        tabelaDiv.innerHTML = html;
      } else {
        tabelaDiv.innerHTML = "<div class='text-secondary small'>Nenhum diagnóstico encontrado.</div>";
      }
    })
    .catch(err => {
      console.error(err);
      alert("Erro ao carregar o dashboard.");
    });
}

// ======= Filtros =======
if (filtroAno) filtroAno.addEventListener("change", fetchDashboard);
if (filtroMes) filtroMes.addEventListener("change", fetchDashboard);
if (filtroCid) filtroCid.addEventListener("change", fetchDashboard);
if (btnLimpar) {
  btnLimpar.addEventListener("click", () => {
    if (filtroAno) filtroAno.value = "";
    if (filtroMes) filtroMes.value = "";
    if (filtroCid) filtroCid.value = "";
    fetchDashboard();
  });
}

// ======= Tema (FAB) =======
function updateThemeButton() {
  const isDark = document.body.classList.contains("theme-dark");
  if (btnToggleTheme) {
    btnToggleTheme.innerHTML = isDark ? '<i class="bi bi-sun"></i>' : '<i class="bi bi-moon"></i>';
    btnToggleTheme.classList.toggle("btn-outline-light", isDark);
    btnToggleTheme.classList.toggle("btn-outline-dark", !isDark);
  }
}
function toggleTheme() {
  const body = document.body;
  if (body.classList.contains("theme-dark")) {
    body.classList.remove("theme-dark");
    body.classList.add("theme-light");
  } else {
    body.classList.remove("theme-light");
    body.classList.add("theme-dark");
  }
  updateThemeButton();
  setTimeout(() => {
    fetchDashboard();
    smartFitKpi(kpiValor);
  }, 150);
}
if (btnToggleTheme) btnToggleTheme.addEventListener("click", toggleTheme);

// ======= Exportar PDF (FAB) =======
function openExport() {
  const params = new URLSearchParams();
  if (filtroAno?.value) params.set("ano", filtroAno.value);
  if (filtroMes?.value) params.set("mes", filtroMes.value);
  if (filtroCid?.value) params.set("cid", filtroCid.value);
  const url = "/export/pdf" + (params.toString() ? `?${params.toString()}` : "");
  window.open(url, "_blank");
}
if (btnExport) btnExport.addEventListener("click", openExport);

// ======= Resize =======
window.addEventListener("resize", () => smartFitKpi(kpiValor));

// ======= Inicial =======
document.addEventListener("DOMContentLoaded", () => {
  updateThemeButton();
  fetchDashboard();
});
