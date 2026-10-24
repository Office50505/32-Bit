from io import BytesIO
from xml.sax.saxutils import escape

from rdkit import Chem, rdBase
from rdkit.Chem import rdDepictor
from rdkit.Chem.Draw import rdMolDraw2D
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.models.analysis import AnalyzeResponse, MoleculeStatus, RunResponse

NAVY = colors.HexColor("#10243A")
TEAL = colors.HexColor("#0B8279")
MUTED = colors.HexColor("#60758A")
LINE = colors.HexColor("#D9E4EA")
PALE = colors.HexColor("#F4F8FA")
RED = colors.HexColor("#C92642")
AMBER = colors.HexColor("#B86A00")


class InvariantCanvas(Canvas):
    def __init__(self, *args: object, **kwargs: object) -> None:
        kwargs["invariant"] = 1
        super().__init__(*args, **kwargs)


def _text(value: object) -> str:
    if value is None:
        return "Unknown - see reason"
    return escape(str(value))


def _depiction_png(result: AnalyzeResponse) -> bytes | None:
    if result.status == MoleculeStatus.INVALID:
        return None
    structure = result.standardized_smiles or result.canonical_smiles
    if not structure:
        return None
    with rdBase.BlockLogs():
        try:
            molecule = Chem.MolFromSmiles(structure)
            if molecule is None:
                return None
            rdDepictor.Compute2DCoords(molecule)
            drawer = rdMolDraw2D.MolDraw2DCairo(720, 300)
            drawer.drawOptions().clearBackground = False
            atoms = sorted(
                {index for issue in result.issues for index in issue.location.atom_indices}
            )
            bonds = sorted(
                {index for issue in result.issues for index in issue.location.bond_indices}
            )
            color = (0.79, 0.06, 0.18, 1.0)
            drawer.DrawMolecule(
                molecule,
                highlightAtoms=atoms,
                highlightBonds=bonds,
                highlightAtomColors={index: color for index in atoms},
                highlightBondColors={index: color for index in bonds},
            )
            drawer.FinishDrawing()
            return drawer.GetDrawingText()
        except Exception:
            return None


def build_run_pdf(run: RunResponse) -> bytes:
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=17 * mm,
        leftMargin=17 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"ProvenanceLab report {run.run_id}",
        author="ProvenanceLab",
        subject="Deterministic molecular validation report",
    )
    base = getSampleStyleSheet()
    title = ParagraphStyle(
        "Title",
        parent=base["Title"],
        fontName="Times-Bold",
        fontSize=24,
        leading=28,
        textColor=NAVY,
        alignment=TA_LEFT,
        spaceAfter=6,
    )
    heading = ParagraphStyle(
        "Heading",
        parent=base["Heading2"],
        fontName="Times-Bold",
        fontSize=15,
        leading=18,
        textColor=NAVY,
        spaceBefore=10,
        spaceAfter=7,
    )
    body = ParagraphStyle(
        "Body",
        parent=base["BodyText"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=NAVY,
    )
    small = ParagraphStyle(
        "Small",
        parent=body,
        fontSize=7.2,
        leading=9.5,
        textColor=MUTED,
    )
    code = ParagraphStyle(
        "Code",
        parent=small,
        fontName="Courier",
        fontSize=6.8,
        leading=9,
        wordWrap="CJK",
    )

    story: list[object] = [
        Paragraph("ProvenanceLab", title),
        Paragraph("Deterministic molecular validation report", heading),
        Paragraph(
            "Research aid only. This report is not a prediction of efficacy or safety. "
            "Missing values are never inferred or silently filled.",
            body,
        ),
        Spacer(1, 8),
        Table(
            [
                ["Run ID", run.run_id],
                ["Structures", str(len(run.results))],
                ["Input SHA-256", run.input_sha256],
                ["Configuration SHA-256", run.configuration_sha256],
                ["Output SHA-256", run.output_sha256],
            ],
            colWidths=[42 * mm, 132 * mm],
            style=TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), PALE),
                    ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
                    ("TEXTCOLOR", (1, 0), (1, -1), NAVY),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTNAME", (1, 0), (1, -1), "Courier"),
                    ("FONTSIZE", (0, 0), (-1, -1), 7),
                    ("GRID", (0, 0), (-1, -1), 0.5, LINE),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            ),
        ),
    ]

    for index, result in enumerate(run.results, start=1):
        story.extend(
            [
                PageBreak(),
                Paragraph(f"{index}. {_text(result.label)}", title),
                Paragraph(
                    f"Overall status: <b>{result.status.value.upper()}</b> | "
                    f"Analysis ID: <font name='Courier'>{_text(result.analysis_id)}</font>",
                    body,
                ),
                Spacer(1, 6),
            ]
        )
        depiction = _depiction_png(result)
        if depiction:
            story.extend(
                [Image(BytesIO(depiction), width=174 * mm, height=72.5 * mm), Spacer(1, 4)]
            )
        story.extend(
            [
                Paragraph("Submitted structure", heading),
                Paragraph(_text(result.raw_input), code),
                Paragraph("Canonical and standardized forms", heading),
                Table(
                    [
                        ["Canonical SMILES", Paragraph(_text(result.canonical_smiles), code)],
                        ["Standardized parent", Paragraph(_text(result.standardized_smiles), code)],
                    ],
                    colWidths=[42 * mm, 132 * mm],
                    style=TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (0, -1), PALE),
                            ("GRID", (0, 0), (-1, -1), 0.5, LINE),
                            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                            ("FONTSIZE", (0, 0), (0, -1), 7.5),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("PADDING", (0, 0), (-1, -1), 5),
                        ]
                    ),
                ),
            ]
        )
        if result.source is not None:
            source = result.source
            source_rows: list[list[object]] = [
                ["Source type", _text(source.source_type)],
                ["Filename", _text(source.filename)],
                ["Extraction", _text(source.extraction_method)],
                ["File SHA-256", _text(source.file_sha256)],
            ]
            if source.page is not None:
                source_rows.append(["Primary page", str(source.page)])
            if source.row is not None:
                source_rows.append(["Primary row", str(source.row)])
            if source.mentions:
                locations = ", ".join(
                    mention.locator
                    or (
                        f"Page {mention.page}"
                        if mention.page is not None
                        else f"Row {mention.row}"
                    )
                    for mention in source.mentions[:20]
                )
                if len(source.mentions) > 20:
                    locations += f", +{len(source.mentions) - 20} more"
                source_rows.append(
                    [
                        "Source mentions",
                        Paragraph(escape(locations), small),
                    ]
                )
            if source.source_excerpt:
                source_rows.append(
                    ["Source excerpt", Paragraph(escape(source.source_excerpt), small)]
                )
            story.extend(
                [
                    Paragraph("Source provenance", heading),
                    Table(
                        source_rows,
                        colWidths=[42 * mm, 132 * mm],
                        style=TableStyle(
                            [
                                ("BACKGROUND", (0, 0), (0, -1), PALE),
                                ("GRID", (0, 0), (-1, -1), 0.4, LINE),
                                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                                ("FONTSIZE", (0, 0), (-1, -1), 6.8),
                                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                ("PADDING", (0, 0), (-1, -1), 4),
                            ]
                        ),
                    ),
                ]
            )
        story.append(Paragraph("Validation findings", heading))
        if result.issues:
            issue_rows = [["Code", "Finding", "Why it matters", "Next step"]]
            for issue in result.issues:
                code_label = issue.code
                if issue.subcode:
                    code_label += f" / {issue.subcode}"
                issue_rows.append(
                    [
                        Paragraph(escape(code_label), code),
                        Paragraph(escape(issue.explanation), small),
                        Paragraph(escape(issue.why_it_matters), small),
                        Paragraph(escape(issue.next_step), small),
                    ]
                )
            issue_table = Table(
                issue_rows,
                colWidths=[33 * mm, 47 * mm, 47 * mm, 47 * mm],
                repeatRows=1,
            )
            issue_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, 0), 7),
                        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("PADDING", (0, 0), (-1, -1), 4),
                    ]
                )
            )
            story.append(issue_table)
        else:
            story.append(
                Paragraph("No validation issue was detected by the configured ruleset.", body)
            )

        story.append(Paragraph("Standardization record", heading))
        if result.standardization_steps:
            step_rows = [["Step", "Outcome", "Before", "After"]]
            for step in result.standardization_steps:
                step_rows.append(
                    [
                        Paragraph(escape(step.label), small),
                        "Changed" if step.changed else "No change",
                        Paragraph(_text(step.before_smiles), code),
                        Paragraph(_text(step.after_smiles), code),
                    ]
                )
            step_table = Table(
                step_rows,
                colWidths=[42 * mm, 20 * mm, 56 * mm, 56 * mm],
                repeatRows=1,
            )
            step_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), TEAL),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, -1), 6.8),
                        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("PADDING", (0, 0), (-1, -1), 4),
                    ]
                )
            )
            story.append(step_table)
        else:
            story.append(Paragraph("Not run because no valid molecular graph was available.", body))

        story.append(Paragraph("Property and evidence audit", heading))
        property_rows = [["Property", "Computed", "Evidence", "Status / reason"]]
        for prop in result.properties:
            computed = _text(prop.computed.value)
            if prop.computed.value is not None and prop.computed.unit:
                computed += f" {escape(prop.computed.unit)}"
            evidence = _text(prop.evidence.value)
            reason = prop.evidence.reason or prop.computed.reason or "Available"
            property_rows.append(
                [
                    Paragraph(escape(prop.label), small),
                    Paragraph(computed, small),
                    Paragraph(evidence, small),
                    Paragraph(
                        f"<b>{escape(prop.comparison_status.value)}</b><br/>{escape(reason)}",
                        small,
                    ),
                ]
            )
        property_table = Table(
            property_rows,
            colWidths=[42 * mm, 30 * mm, 30 * mm, 72 * mm],
            repeatRows=1,
        )
        property_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.4, LINE),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("PADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.extend(
            [
                property_table,
                Paragraph("Provenance", heading),
                Table(
                    [
                        ["Input SHA-256", result.manifest.input_sha256],
                        ["Configuration SHA-256", result.manifest.configuration_sha256],
                        ["Output SHA-256", result.manifest.output_sha256],
                        ["RDKit", result.manifest.tool_versions.rdkit],
                        ["Ruleset", result.manifest.tool_versions.ruleset],
                        ["Evidence snapshot", result.manifest.snapshot_id],
                    ],
                    colWidths=[42 * mm, 132 * mm],
                    style=TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (0, -1), PALE),
                            ("GRID", (0, 0), (-1, -1), 0.4, LINE),
                            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                            ("FONTNAME", (1, 0), (1, -1), "Courier"),
                            ("FONTSIZE", (0, 0), (-1, -1), 6.8),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("PADDING", (0, 0), (-1, -1), 4),
                        ]
                    ),
                ),
            ]
        )

    def footer(canvas: Canvas, _document: SimpleDocTemplate) -> None:
        canvas.saveState()
        canvas.setStrokeColor(LINE)
        canvas.line(17 * mm, 12 * mm, 193 * mm, 12 * mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(17 * mm, 7.5 * mm, run.run_id)
        canvas.drawRightString(193 * mm, 7.5 * mm, f"Page {canvas.getPageNumber()}")
        canvas.restoreState()

    document.build(
        story,
        onFirstPage=footer,
        onLaterPages=footer,
        canvasmaker=InvariantCanvas,
    )
    return output.getvalue()
