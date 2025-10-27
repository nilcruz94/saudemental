import os
import io
import json
import pandas as pd
from datetime import datetime
from flask import Flask, render_template, jsonify, request, send_file

# ==== ReportLab (PDF) ====
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Flowable
)
from reportlab.graphics.shapes import Drawing, Circle, String
from reportlab.graphics import renderPDF
from reportlab.pdfgen import canvas as canvas_mod  # para canvas numerado

app = Flask(__name__)

# Caminhos
DATA_DIR = r"C:\Users\Neto\Desktop\saudemental\data\csv\anuais\limpos\finais"
CID_FILE = r"C:\Users\Neto\Desktop\saudemental\data\cid10_F00_F99.csv"
LOGO_PATH = os.path.join(app.root_path, "static", "img", "logo.png")

# Cache
DATAFRAME_CACHE = None
CID_DICT = None

# Meses
MESES_PT = {1:"Janeiro",2:"Fevereiro",3:"Março",4:"Abril",5:"Maio",6:"Junho",
            7:"Julho",8:"Agosto",9:"Setembro",10:"Outubro",11:"Novembro",12:"Dezembro"}
MESES_PT_CURTOS = {1:"Jan",2:"Fev",3:"Mar",4:"Abr",5:"Mai",6:"Jun",
                   7:"Jul",8:"Ago",9:"Set",10:"Out",11:"Nov",12:"Dez"}

# ---------- Carga / preparo ----------
def carregar_cids():
    global CID_DICT
    if CID_DICT is not None:
        return CID_DICT
    if os.path.exists(CID_FILE):
        cid_df = pd.read_csv(CID_FILE, sep=";", encoding="utf-8")
        CID_DICT = dict(zip(cid_df["CID"], cid_df["Descricao"]))
    else:
        CID_DICT = {}
    return CID_DICT

def carregar_dados():
    global DATAFRAME_CACHE
    if DATAFRAME_CACHE is not None:
        return DATAFRAME_CACHE

    dfs = []
    for file in os.listdir(DATA_DIR):
        if file.endswith(".csv") and file.startswith("SIH_"):
            path = os.path.join(DATA_DIR, file)
            df = pd.read_csv(path, sep=";", dtype=str, encoding="utf-8")
            dfs.append(df)

    if not dfs:
        DATAFRAME_CACHE = pd.DataFrame(columns=[
            "ANO_CMPT","MES_CMPT","MUNIC_RES","DIAG_PRINC","SEXO",
            "IDADE","DIAS_PERM","MORTE","VAL_TOT","CID3","MES_NOME","FAIXA_IDADE"
        ])
        return DATAFRAME_CACHE

    df = pd.concat(dfs, ignore_index=True)

    # Tipos
    for col in ["ANO_CMPT","MES_CMPT","IDADE","DIAS_PERM","MORTE"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "VAL_TOT" in df.columns:
        df["VAL_TOT"] = df["VAL_TOT"].astype(str).str.replace(",", ".", regex=False)
        df["VAL_TOT"] = pd.to_numeric(df["VAL_TOT"], errors="coerce")

    # Sexo
    if "SEXO" in df.columns:
        df["SEXO"] = df["SEXO"].map({"1":"Masculino","3":"Feminino","0":"Ignorado"}).fillna("Ignorado")

    # CID
    if "DIAG_PRINC" in df.columns:
        df["DIAG_PRINC"] = df["DIAG_PRINC"].fillna("Ignorado")
        df["CID3"] = df["DIAG_PRINC"].str[:3]
    else:
        df["CID3"] = "Ignorado"

    # Faixas etárias
    def faixa_idade(v):
        if pd.isna(v): return "Ignorado"
        v = int(v)
        if v < 5: return "0–4"
        if v < 10: return "5–9"
        if v < 15: return "10–14"
        if v < 18: return "15–17"
        if v < 30: return "18–29"
        if v < 45: return "30–44"
        if v < 60: return "45–59"
        if v < 75: return "60–74"
        return "75+"
    df["FAIXA_IDADE"] = df["IDADE"].apply(faixa_idade) if "IDADE" in df.columns else "Ignorado"

    # Meses curtos
    if "MES_CMPT" in df.columns:
        df["MES_NOME"] = df["MES_CMPT"].map(MESES_PT_CURTOS)

    DATAFRAME_CACHE = df
    return DATAFRAME_CACHE

def aplicar_filtros(df, ano=None, mes=None, cid=None):
    if ano: df = df[df["ANO_CMPT"] == int(ano)]
    if mes: df = df[df["MES_CMPT"] == int(mes)]
    if cid: df = df[df["CID3"] == cid]
    return df

# ---------- Rotas ----------
@app.route("/")
def index():
    df = carregar_dados()
    anos = (df["ANO_CMPT"].dropna().drop_duplicates().sort_values().astype(int).tolist()
            if "ANO_CMPT" in df.columns else [])
    cids = carregar_cids()
    return render_template("index.html", anos=anos, cids=cids)

@app.route("/api/dashboard")
def api_dashboard():
    ano = request.args.get("ano")
    mes = request.args.get("mes")
    cid = request.args.get("cid")

    df_total = carregar_dados()
    df = aplicar_filtros(df_total, ano, mes, cid)
    cid_dict = carregar_cids()

    # KPIs
    total_internacoes = int(df.shape[0])
    media_dias = float(df["DIAS_PERM"].mean()) if "DIAS_PERM" in df.columns and not df["DIAS_PERM"].isna().all() else 0.0
    total_obitos = int(df["MORTE"].fillna(0).sum()) if "MORTE" in df.columns else 0
    valor_total = float(df["VAL_TOT"].sum()) if "VAL_TOT" in df.columns and not df["VAL_TOT"].isna().all() else 0.0

    # Ano (categórico)
    by_year = []
    if df.shape[0]:
        tmpy = df.groupby("ANO_CMPT").size().reset_index(name="internacoes").sort_values("ANO_CMPT")
        tmpy["ANO_CMPT"] = tmpy["ANO_CMPT"].astype("Int64").astype(str)
        by_year = tmpy.to_dict(orient="records")

    # Mensal (Jan..Dez com zeros) — só se ano for passado
    by_month = []
    if ano:
        meses = pd.DataFrame({"MES_CMPT": range(1,13)})
        grp = df.groupby("MES_CMPT", dropna=False).size().reset_index(name="internacoes")
        out = meses.merge(grp, on="MES_CMPT", how="left").fillna({"internacoes":0}).sort_values("MES_CMPT")
        out["MES_NOME"] = out["MES_CMPT"].map(MESES_PT_CURTOS)
        out["internacoes"] = out["internacoes"].astype(int)
        by_month = out[["MES_CMPT","MES_NOME","internacoes"]].to_dict(orient="records")

    # Quebras
    by_sex = (df.groupby("SEXO").size().reset_index(name="internacoes").to_dict(orient="records")
              if "SEXO" in df.columns and df.shape[0] else [])
    by_age = (df.groupby("FAIXA_IDADE").size().reset_index(name="internacoes")
              .sort_values("FAIXA_IDADE").to_dict(orient="records")
              if "FAIXA_IDADE" in df.columns and df.shape[0] else [])

    # Top CIDs
    by_cid_top = []
    if "CID3" in df.columns and df.shape[0]:
        tmpc = (df.groupby("CID3").size().reset_index(name="internacoes")
                .sort_values("internacoes", ascending=False).head(10))
        tmpc["Descricao"] = tmpc["CID3"].map(cid_dict).fillna("Descrição não encontrada")
        by_cid_top = tmpc.to_dict(orient="records")

    return jsonify({
        "kpis": {
            "total_internacoes": total_internacoes,
            "media_dias": round(media_dias, 2),
            "total_obitos": total_obitos,
            "valor_total": round(valor_total, 2)
        },
        "series": {"by_year": by_year, "by_month": by_month},
        "breakdowns": {"by_sex": by_sex, "by_age": by_age, "by_cid_top": by_cid_top}
    })

# ---------- PDF estilizado e centralizado ----------
PRIMARY   = colors.HexColor("#0f172a")
SECONDARY = colors.HexColor("#1e293b")
ACCENT    = colors.HexColor("#3b82f6")
LIGHT_BG  = colors.HexColor("#f8fafc")
LIGHTER   = colors.HexColor("#f1f5f9")
GRID      = colors.HexColor("#cbd5e1")
TXT_DARK  = colors.HexColor("#0f172a")
TXT_MUTE  = colors.HexColor("#475569")

def _fmt_int(v):  return f"{int(v):,}".replace(",", ".")
def _fmt_real(v): return f"{float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X",".")

class LogoFallback(Flowable):
    def __init__(self, size=18):
        Flowable.__init__(self)
        self.size = size
        self.width = self.height = size
    def draw(self):
        d = Drawing(self.size, self.size)
        d.add(Circle(self.size/2, self.size/2, self.size/2, fillColor=ACCENT, strokeColor=ACCENT))
        d.add(String(self.size/2, self.size/2-4, "SM", textAnchor="middle",
                     fontName="Helvetica-Bold", fontSize=8, fillColor=colors.white))
        renderPDF.draw(d, self.canv, 0, 0)

# Canvas com numeração "X de Y"
class NumberedCanvas(canvas_mod.Canvas):
    def __init__(self, *args, **kwargs):
        canvas_mod.Canvas.__init__(self, *args, **kwargs)
        self._saved_page_states = []
    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()
    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            canvas_mod.Canvas.showPage(self)
        canvas_mod.Canvas.save(self)
    def draw_page_number(self, page_count):
        w, h = A4
        # linha
        self.setStrokeColor(LIGHTER)
        self.line(1.8*cm, 20, w-1.8*cm, 20)
        # esquerda
        self.setFont("Helvetica", 8)
        self.setFillColor(TXT_MUTE)
        self.drawString(1.8*cm, 8, "Relatório gerado pelo Painel Saúde Mental")
        # centro: data/hora
        self.drawCentredString(w/2, 8, datetime.now().strftime("%d/%m/%Y %H:%M"))
        # direita: página X de Y
        self.drawRightString(w-1.8*cm, 8, f"Página {self._pageNumber} de {page_count}")

def _filters_box(doc_width, ano, mes_txt, cid, cid_desc):
    styles = getSampleStyleSheet()
    label = Paragraph('<b>Filtros aplicados</b>', ParagraphStyle("lab", parent=styles["Normal"], textColor=ACCENT, fontSize=10))
    texto = f"Ano: {ano or 'Todos'} | Mês: {mes_txt}"
    if cid:
        texto += f" | CID: {cid}" + (f" – {cid_desc}" if cid_desc else "")
    val = Paragraph(texto, ParagraphStyle("val", parent=styles["Normal"], textColor=TXT_DARK, fontSize=9))
    tbl = Table([[label, val]], colWidths=[3.5*cm, doc_width-3.5*cm], hAlign="CENTER")
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), LIGHTER),
        ("BOX", (0,0), (-1,-1), 0.5, ACCENT),
        ("INNERGRID", (0,0), (-1,-1), 0.25, GRID),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING",(0,0), (-1,-1), 8),
        ("RIGHTPADDING",(0,0), (-1,-1), 8),
        ("TOPPADDING",(0,0), (-1,-1), 6),
        ("BOTTOMPADDING",(0,0), (-1,-1), 6),
    ]))
    return tbl

def _section_title_center(text, doc_width):
    styles = getSampleStyleSheet()
    title = Paragraph(f"<b>{text}</b>", ParagraphStyle(
        "SecTitle",
        parent=styles["Heading3"],
        alignment=1,  # center
        fontSize=12,
        textColor=TXT_DARK,
        spaceBefore=10, spaceAfter=4, leading=16
    ))
    underline = Table([[""]], colWidths=[doc_width*0.18], hAlign="CENTER")
    underline.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (0,0), ACCENT),
        ("TOPPADDING",(0,0),(0,0),0),
        ("BOTTOMPADDING",(0,0),(0,0),0),
        ("LEFTPADDING",(0,0),(0,0),0),
        ("RIGHTPADDING",(0,0),(0,0),0),
        ("BOX",(0,0),(0,0),0.1,ACCENT),
    ]))
    return [title, underline, Spacer(1, 4)]

def _zebra_table(headers, rows, widths, right_cols=None):
    """Tabela centralizada com wrap e números à direita."""
    styles = getSampleStyleSheet()
    cell = ParagraphStyle("cell", parent=styles["Normal"], fontSize=9, leading=12, textColor=TXT_DARK)

    wrapped_rows = []
    for r in rows:
        new_r = [Paragraph(str(val), cell) for val in r]
        wrapped_rows.append(new_r)

    data = [headers] + wrapped_rows
    tbl = Table(data, colWidths=widths, hAlign="CENTER")
    style = [
        ("BACKGROUND", (0,0), (-1,0), SECONDARY),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME",  (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",  (0,0), (-1,0), 10),
        ("GRID",      (0,0), (-1,-1), 0.25, GRID),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, LIGHT_BG]),
        ("FONTSIZE",  (0,1), (-1,-1), 9),
        ("VALIGN",    (0,1), (-1,-1), "TOP"),
        ("LEFTPADDING", (0,0), (-1,-1), 6),
        ("RIGHTPADDING",(0,0), (-1,-1), 6),
        ("TOPPADDING",  (0,0), (-1,-1), 4),
        ("BOTTOMPADDING",(0,0), (-1,-1), 4),
    ]
    if right_cols:
        for c in right_cols:
            style.append(("ALIGN", (c,1), (c,-1), "RIGHT"))
    tbl.setStyle(TableStyle(style))
    return tbl

def _kpi_cards(total_internacoes, media_dias, total_obitos, valor_total, doc_width):
    data = [
        ["Internações", _fmt_int(total_internacoes), "Média de Dias", f"{media_dias:.2f}"],
        ["Óbitos", _fmt_int(total_obitos), "Valor Total (R$)", _fmt_real(valor_total)],
    ]
    w = doc_width
    widths = [0.28*w, 0.22*w, 0.28*w, 0.22*w]
    tbl = Table(data, colWidths=widths, hAlign="CENTER")
    tbl.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.25, GRID),
        ("BACKGROUND", (0,0), (-1,-1), LIGHTER),
        ("TEXTCOLOR", (0,0), (-1,-1), TXT_DARK),
        ("FONTNAME", (0,0), (-1,-1), "Helvetica"),
        ("FONTSIZE", (0,0), (-1,-1), 10),
        ("BACKGROUND", (0,0), (0,-1), LIGHT_BG),
        ("BACKGROUND", (2,0), (2,-1), LIGHT_BG),
        ("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTNAME", (2,0), (2,-1), "Helvetica-Bold"),
        ("ALIGN", (1,0), (1,-1), "RIGHT"),
        ("ALIGN", (3,0), (3,-1), "RIGHT"),
        ("LEFTPADDING", (0,0), (-1,-1), 8),
        ("RIGHTPADDING",(0,0), (-1,-1), 8),
        ("TOPPADDING", (0,0), (-1,-1), 8),
        ("BOTTOMPADDING",(0,0), (-1,-1), 8),
    ]))
    return tbl

# ---------- Export PDF ----------
@app.route("/export/pdf")
def export_pdf():
    ano = request.args.get("ano")
    mes = request.args.get("mes")
    cid = request.args.get("cid")

    df_total = carregar_dados()
    df = aplicar_filtros(df_total, ano, mes, cid)
    cid_dict = carregar_cids()

    # KPIs
    total_internacoes = int(df.shape[0])
    media_dias = float(df["DIAS_PERM"].mean()) if "DIAS_PERM" in df.columns and not df["DIAS_PERM"].isna().all() else 0.0
    total_obitos = int(df["MORTE"].fillna(0).sum()) if "MORTE" in df.columns else 0
    valor_total = float(df["VAL_TOT"].sum()) if "VAL_TOT" in df.columns and not df["VAL_TOT"].isna().all() else 0.0

    # Séries
    by_year = []
    if df.shape[0]:
        tmpy = df.groupby("ANO_CMPT").size().reset_index(name="internacoes").sort_values("ANO_CMPT")
        tmpy["ANO_CMPT"] = tmpy["ANO_CMPT"].astype("Int64").astype(str)
        by_year = tmpy[["ANO_CMPT","internacoes"]].values.tolist()

    by_month = []
    if ano:
        meses = pd.DataFrame({"MES_CMPT": range(1,13)})
        grp = df.groupby("MES_CMPT", dropna=False).size().reset_index(name="internacoes")
        out = meses.merge(grp, on="MES_CMPT", how="left").fillna({"internacoes":0}).sort_values("MES_CMPT")
        out["MES_NOME"] = out["MES_CMPT"].map(MESES_PT_CURTOS)
        out["internacoes"] = out["internacoes"].astype(int)
        by_month = out[["MES_NOME","internacoes"]].values.tolist()

    by_sex = (df.groupby("SEXO").size().reset_index(name="internacoes")[["SEXO","internacoes"]].values.tolist()
              if "SEXO" in df.columns and df.shape[0] else [])
    by_age = (df.groupby("FAIXA_IDADE").size().reset_index(name="internacoes")[["FAIXA_IDADE","internacoes"]]
              .sort_values("FAIXA_IDADE").values.tolist()
              if "FAIXA_IDADE" in df.columns and df.shape[0] else [])
    by_cid_top = []
    if "CID3" in df.columns and df.shape[0]:
        tmpc = (df.groupby("CID3").size().reset_index(name="internacoes")
                .sort_values("internacoes", ascending=False).head(10))
        tmpc["Descricao"] = tmpc["CID3"].map(cid_dict).fillna("Descrição não encontrada")
        by_cid_top = tmpc[["CID3","Descricao","internacoes"]].values.tolist()

    # Montagem
    buff = io.BytesIO()
    doc = SimpleDocTemplate(
        buff, pagesize=A4,
        leftMargin=1.8*cm, rightMargin=1.8*cm,
        topMargin=2.2*cm, bottomMargin=2.0*cm
    )
    doc_width = doc.width

    styles = getSampleStyleSheet()
    story = []

    # Caixa de filtros (mais destacada)
    mes_txt = MESES_PT.get(int(mes), "Todos") if mes else "Todos"
    cid_desc = cid_dict.get(cid, "") if cid else ""
    story.append(_filters_box(doc_width, ano, mes_txt, cid, cid_desc))
    story.append(Spacer(1, 10))

    # KPIs (central)
    story.append(_kpi_cards(total_internacoes, media_dias, total_obitos, valor_total, doc_width))
    story.append(Spacer(1, 8))

    # Blocos com títulos centralizados
    if by_year:
        story += _section_title_center("Internações por Ano", doc_width)
        story.append(_zebra_table(
            ["Ano","Internações"],
            [[r[0], _fmt_int(r[1])] for r in by_year],
            widths=[3*cm, 4*cm],
            right_cols=[1]
        ))
        story.append(Spacer(1, 8))

    if ano and by_month:
        story += _section_title_center(f"Distribuição Mensal ({ano})", doc_width)
        story.append(_zebra_table(
            ["Mês","Internações"],
            [[r[0], _fmt_int(r[1])] for r in by_month],
            widths=[3.2*cm, 4*cm],
            right_cols=[1]
        ))
        story.append(Spacer(1, 8))

    if by_sex:
        story += _section_title_center("Distribuição por Sexo", doc_width)
        story.append(_zebra_table(
            ["Sexo","Internações"],
            [[s, _fmt_int(v)] for s, v in by_sex],
            widths=[4.2*cm, 4*cm],
            right_cols=[1]
        ))
        story.append(Spacer(1, 8))

    if by_age:
        story += _section_title_center("Internações por Faixa Etária", doc_width)
        story.append(_zebra_table(
            ["Faixa Etária","Internações"],
            [[a, _fmt_int(v)] for a, v in by_age],
            widths=[4.2*cm, 4*cm],
            right_cols=[1]
        ))
        story.append(Spacer(1, 8))

    if by_cid_top:
        story += _section_title_center("Top 10 Diagnósticos (CID-10)", doc_width)
        cid_w, val_w = 2.0*cm, 3.0*cm
        desc_w = doc_width - cid_w - val_w
        story.append(_zebra_table(
            ["CID","Descrição","Internações"],
            [[c, d, _fmt_int(v)] for c, d, v in by_cid_top],
            widths=[cid_w, desc_w, val_w],
            right_cols=[2]
        ))

    # Cabeçalho por página + rodapé aprimorado com "X de Y"
    def _header(canvas, doc_):
        w, h = A4
        hh = 28
        canvas.saveState()
        # faixa
        canvas.setFillColor(PRIMARY)
        canvas.rect(0, h-hh, w, hh, fill=1, stroke=0)
        # logo
        x0 = doc_.leftMargin
        if os.path.exists(LOGO_PATH):
            canvas.drawImage(LOGO_PATH, x0, h-hh+4, width=20, height=20, mask='auto')
        else:
            canvas.setFillColor(ACCENT); canvas.circle(x0+10, h-hh+14, 9, fill=1, stroke=0)
        # título
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 12)
        canvas.drawString(x0+28, h-hh+9, "Painel Saúde Mental — Relatório do Dashboard")
        canvas.restoreState()

    doc.build(story, onFirstPage=_header, onLaterPages=_header, canvasmaker=NumberedCanvas)
    buff.seek(0)
    filename = f"relatorio_{ano or 'todos'}_{cid or 'todos'}.pdf"
    return send_file(buff, mimetype="application/pdf", as_attachment=True, download_name=filename)

if __name__ == "__main__":
    app.run(debug=True)
