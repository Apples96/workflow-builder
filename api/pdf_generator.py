"""
PDF Generator for Workflow Execution Reports

This module provides functionality to generate professional PDF reports
for workflow execution results. Reports are clean, neutral, and suitable
for end-clients without any vendor branding.

Key Features:
    - Professional formatting with headers, sections, and styling
    - Support for structured data (dictionaries, lists, nested objects)
    - Automatic page breaks for long content
    - Date/time stamping
    - Clean, neutral design suitable for any business
"""

from datetime import datetime
from io import BytesIO
from typing import Dict, Any, Optional, List
import json
import re

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    KeepTogether,
    HRFlowable
)
from reportlab.pdfgen import canvas


class PDFReportGenerator:
    """
    Generator for workflow execution PDF reports.

    Creates professional, well-formatted PDF documents containing
    workflow execution results in a clean, business-appropriate style.
    """

    def __init__(self):
        """Initialize PDF generator with default styles."""
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _setup_custom_styles(self):
        """Create custom paragraph styles for the report."""
        # Title style
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Title'],
            fontSize=24,
            textColor=colors.HexColor('#1a1a1a'),
            spaceAfter=30,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        ))

        # Section heading style
        self.styles.add(ParagraphStyle(
            name='SectionHeading',
            parent=self.styles['Heading1'],
            fontSize=16,
            textColor=colors.HexColor('#2c3e50'),
            spaceAfter=12,
            spaceBefore=20,
            fontName='Helvetica-Bold'
        ))

        # Subsection heading style
        self.styles.add(ParagraphStyle(
            name='SubHeading',
            parent=self.styles['Heading2'],
            fontSize=13,
            textColor=colors.HexColor('#34495e'),
            spaceAfter=8,
            spaceBefore=12,
            fontName='Helvetica-Bold'
        ))

        # Body text style
        self.styles.add(ParagraphStyle(
            name='CustomBodyText',
            parent=self.styles['Normal'],
            fontSize=11,
            textColor=colors.HexColor('#2c3e50'),
            spaceAfter=8,
            leading=14,
            fontName='Helvetica'
        ))

        # Footer style
        self.styles.add(ParagraphStyle(
            name='Footer',
            parent=self.styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#7f8c8d'),
            alignment=TA_CENTER,
            fontName='Helvetica-Oblique'
        ))

        # Markdown H1 style (# Title)
        self.styles.add(ParagraphStyle(
            name='MarkdownH1',
            parent=self.styles['Title'],
            fontSize=20,
            textColor=colors.HexColor('#1a1a1a'),
            spaceAfter=16,
            spaceBefore=12,
            fontName='Helvetica-Bold'
        ))

        # Markdown H2 style (## Section)
        self.styles.add(ParagraphStyle(
            name='MarkdownH2',
            parent=self.styles['Heading1'],
            fontSize=16,
            textColor=colors.HexColor('#2c3e50'),
            spaceAfter=12,
            spaceBefore=16,
            fontName='Helvetica-Bold'
        ))

        # Markdown H3 style (### Subsection)
        self.styles.add(ParagraphStyle(
            name='MarkdownH3',
            parent=self.styles['Heading2'],
            fontSize=13,
            textColor=colors.HexColor('#34495e'),
            spaceAfter=8,
            spaceBefore=12,
            fontName='Helvetica-Bold'
        ))

        # Markdown H4 style (#### Detail)
        self.styles.add(ParagraphStyle(
            name='MarkdownH4',
            parent=self.styles['Heading3'],
            fontSize=11,
            textColor=colors.HexColor('#34495e'),
            spaceAfter=6,
            spaceBefore=8,
            fontName='Helvetica-Bold'
        ))

        # Bullet list style
        self.styles.add(ParagraphStyle(
            name='BulletList',
            parent=self.styles['Normal'],
            fontSize=11,
            textColor=colors.HexColor('#2c3e50'),
            spaceAfter=4,
            leftIndent=20,
            bulletIndent=10,
            fontName='Helvetica'
        ))

    def generate_report(
        self,
        workflow_name: str,
        workflow_description: str,
        execution_result: str,
        execution_status: str,
        execution_time: Optional[float] = None,
        execution_date: Optional[datetime] = None,
        workflow_id: Optional[str] = None,
        execution_id: Optional[str] = None
    ) -> BytesIO:
        """
        Generate a PDF report for a workflow execution.

        Args:
            workflow_name: Name of the workflow
            workflow_description: Description of what the workflow does
            execution_result: The result/output from workflow execution
            execution_status: Status of execution (success, failed, etc.)
            execution_time: Time taken to execute (in seconds)
            execution_date: When the workflow was executed
            workflow_id: Unique workflow identifier
            execution_id: Unique execution identifier

        Returns:
            BytesIO: PDF file as bytes buffer, ready to be sent to client
        """
        # Create buffer to hold PDF in memory
        buffer = BytesIO()

        # Create PDF document
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=2*cm,
            leftMargin=2*cm,
            topMargin=2*cm,
            bottomMargin=2*cm,
            title=f"Workflow Execution Report - {workflow_name}",
            author="Workflow Automation System"
        )

        # Build story (content elements)
        story = []

        # Add title
        story.append(Paragraph("Workflow Execution Report", self.styles['CustomTitle']))
        story.append(Spacer(1, 0.5*cm))

        # Add execution date/time
        if execution_date:
            date_str = execution_date.strftime("%d/%m/%Y %H:%M:%S")
        else:
            date_str = datetime.utcnow().strftime("%d/%m/%Y %H:%M:%S")

        story.append(Paragraph(
            f"<i>Generated on {date_str}</i>",
            self.styles['Footer']
        ))
        story.append(Spacer(1, 1*cm))

        # Section 1: Workflow Information
        story.append(Paragraph("Workflow Information", self.styles['SectionHeading']))

        # Workflow Name
        story.append(Paragraph(
            f"<b>Workflow Name:</b> {workflow_name or 'Unnamed Workflow'}",
            self.styles['CustomBodyText']
        ))

        # Description - use Paragraph instead of Table to allow page breaks
        story.append(Paragraph("<b>Description:</b>", self.styles['CustomBodyText']))

        # Escape and format description text
        description_text = workflow_description or "No description provided"
        # Escape XML special characters
        safe_description = (description_text
                           .replace('&', '&amp;')
                           .replace('<', '&lt;')
                           .replace('>', '&gt;')
                           .replace('\n', '<br/>'))  # Preserve line breaks

        story.append(Paragraph(safe_description, self.styles['CustomBodyText']))
        story.append(Spacer(1, 0.3*cm))

        # IDs in a table (these are short and won't cause issues)
        if workflow_id or execution_id:
            id_data = []
            if workflow_id:
                id_data.append(["Workflow ID:", workflow_id])
            if execution_id:
                id_data.append(["Execution ID:", execution_id])

            id_table = Table(id_data, colWidths=[4*cm, 13*cm])
            id_table.setStyle(TableStyle([
                ('FONT', (0, 0), (0, -1), 'Helvetica-Bold', 11),
                ('FONT', (1, 0), (1, -1), 'Helvetica', 11),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#2c3e50')),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ]))
            story.append(id_table)

        story.append(Spacer(1, 1*cm))

        # Section 2: Execution Status
        story.append(Paragraph("Execution Status", self.styles['SectionHeading']))

        # Status color based on result
        status_color = colors.HexColor('#27ae60') if execution_status.lower() in ['success', 'completed'] else colors.HexColor('#e74c3c')

        status_data = [
            ["Status:", execution_status.upper()],
        ]

        if execution_time is not None:
            status_data.append(["Execution Time:", f"{execution_time:.2f} seconds"])

        status_table = Table(status_data, colWidths=[4*cm, 13*cm])
        status_table.setStyle(TableStyle([
            ('FONT', (0, 0), (0, -1), 'Helvetica-Bold', 11),
            ('FONT', (1, 0), (1, -1), 'Helvetica-Bold', 11),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#2c3e50')),
            ('TEXTCOLOR', (1, 0), (1, 0), status_color),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))

        story.append(status_table)
        story.append(Spacer(1, 1*cm))

        # Section 3: Execution Results
        story.append(Paragraph("Execution Results", self.styles['SectionHeading']))
        story.append(Spacer(1, 0.3*cm))

        # Format results based on content type
        result_elements = self._format_result(execution_result)
        story.extend(result_elements)

        # Add footer
        story.append(Spacer(1, 2*cm))
        story.append(Paragraph(
            "<i>This report was automatically generated by the Workflow Automation System</i>",
            self.styles['Footer']
        ))

        # Build PDF
        doc.build(story)

        # Reset buffer position to beginning
        buffer.seek(0)

        return buffer

    def _format_result(self, result: str) -> list:
        """
        Format execution result for PDF display.

        Attempts to parse result as JSON for structured display,
        then tries Markdown parsing, falls back to plain text.

        Args:
            result: The execution result string

        Returns:
            List of ReportLab flowables (paragraphs, tables, etc.)
        """
        elements = []

        # Try to parse as JSON for better formatting
        try:
            result_data = json.loads(result)
            elements.extend(self._format_json_data(result_data))
        except (json.JSONDecodeError, TypeError):
            # Not JSON - check if it's Markdown
            if self._is_markdown(result):
                elements.extend(self._parse_markdown(result))
            else:
                # Plain text
                lines = result.split('\n')
                for line in lines:
                    if line.strip():
                        # Escape XML special characters
                        safe_line = (line
                                    .replace('&', '&amp;')
                                    .replace('<', '&lt;')
                                    .replace('>', '&gt;'))
                        elements.append(Paragraph(safe_line, self.styles['CustomBodyText']))
                    else:
                        elements.append(Spacer(1, 0.2*cm))

        return elements

    def _is_markdown(self, text: str) -> bool:
        """
        Detect if text contains Markdown formatting.

        Args:
            text: Text to check

        Returns:
            True if Markdown detected, False otherwise
        """
        # Check for common Markdown patterns
        markdown_patterns = [
            r'^#{1,4}\s+\w+',  # Headers (# Title)
            r'\*\*\w+\*\*',     # Bold (**text**)
            r'^[-*•]\s+\w+',    # Bullet lists
            r'^---+$',          # Horizontal rules
            r'^\d+\.\s+\w+',    # Numbered lists
            r'^\|.*\|.*\|$',    # Tables
        ]

        for pattern in markdown_patterns:
            if re.search(pattern, text, re.MULTILINE):
                return True
        return False

    def _parse_markdown(self, markdown_text: str) -> List:
        """
        Parse Markdown text and convert to ReportLab flowables.

        Supports:
        - Headers (# ## ### ####)
        - Bold text (**text**)
        - Bullet lists (-, •, *)
        - Numbered lists (1. 2. 3.)
        - Horizontal rules (---)
        - Tables (| col1 | col2 |)

        Args:
            markdown_text: Markdown formatted text

        Returns:
            List of ReportLab flowables
        """
        elements = []
        lines = markdown_text.split('\n')
        i = 0

        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # Skip empty lines
            if not stripped:
                elements.append(Spacer(1, 0.2*cm))
                i += 1
                continue

            # Horizontal rule (--- or %%%)
            if re.match(r'^[-=%]{3,}$', stripped):
                elements.append(Spacer(1, 0.3*cm))
                elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#bdc3c7')))
                elements.append(Spacer(1, 0.3*cm))
                i += 1
                continue

            # Headers (# ## ### ####)
            header_match = re.match(r'^(#{1,4})\s+(.+)$', stripped)
            if header_match:
                level = len(header_match.group(1))
                title = header_match.group(2)

                # Remove markdown formatting from title
                title_clean = self._clean_markdown_inline(title)

                # Choose style based on level
                if level == 1:
                    style = self.styles['MarkdownH1']
                elif level == 2:
                    style = self.styles['MarkdownH2']
                elif level == 3:
                    style = self.styles['MarkdownH3']
                else:
                    style = self.styles['MarkdownH4']

                elements.append(Paragraph(title_clean, style))
                i += 1
                continue

            # Bullet list (-, •, *, ✓)
            bullet_match = re.match(r'^[-•*✓]\s+(.+)$', stripped)
            if bullet_match:
                content = bullet_match.group(1)
                content_clean = self._clean_markdown_inline(content)
                elements.append(Paragraph(f"• {content_clean}", self.styles['BulletList']))
                i += 1
                continue

            # Numbered list (1. 2. 3.)
            numbered_match = re.match(r'^(\d+)\.\s+(.+)$', stripped)
            if numbered_match:
                number = numbered_match.group(1)
                content = numbered_match.group(2)
                content_clean = self._clean_markdown_inline(content)
                elements.append(Paragraph(f"{number}. {content_clean}", self.styles['BulletList']))
                i += 1
                continue

            # Markdown table
            if '|' in stripped and stripped.count('|') >= 2:
                table_lines = []
                j = i
                while j < len(lines) and '|' in lines[j]:
                    table_lines.append(lines[j])
                    j += 1

                if len(table_lines) >= 2:  # At least header + separator
                    table_element = self._parse_markdown_table(table_lines)
                    if table_element:
                        elements.append(table_element)
                        elements.append(Spacer(1, 0.5*cm))
                        i = j
                        continue

            # Regular paragraph
            para_clean = self._clean_markdown_inline(stripped)
            elements.append(Paragraph(para_clean, self.styles['CustomBodyText']))
            i += 1

        return elements

    def _clean_markdown_inline(self, text: str) -> str:
        """
        Clean inline Markdown formatting and convert to ReportLab XML.

        Args:
            text: Text with Markdown inline formatting

        Returns:
            Text with ReportLab XML formatting
        """
        # Escape XML special characters first
        text = (text.replace('&', '&amp;')
                   .replace('<', '&lt;')
                   .replace('>', '&gt;'))

        # Convert **bold** to <b>bold</b>
        text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)

        # Convert *italic* to <i>italic</i>
        text = re.sub(r'(?<!\*)\*(?!\*)(.+?)\*(?!\*)', r'<i>\1</i>', text)

        # Remove emojis that might cause font issues (keep common ones)
        # Common emojis are kept as they usually render fine

        return text

    def _parse_markdown_table(self, table_lines: List[str]) -> Optional[Table]:
        """
        Parse a Markdown table into a ReportLab Table.

        Args:
            table_lines: Lines of the Markdown table

        Returns:
            ReportLab Table or None if parsing fails
        """
        try:
            # Parse table data
            table_data = []
            for line in table_lines:
                # Skip separator line (|---|---|)
                if re.match(r'^\s*\|[-:\s|]+\|\s*$', line):
                    continue

                # Split by | and clean
                cells = [cell.strip() for cell in line.split('|')]
                # Remove empty first/last cells (from leading/trailing |)
                if cells and not cells[0]:
                    cells = cells[1:]
                if cells and not cells[-1]:
                    cells = cells[:-1]

                if cells:
                    # Clean markdown from cells
                    cells_clean = [self._clean_markdown_inline(cell) for cell in cells]
                    table_data.append(cells_clean)

            if not table_data:
                return None

            # Create table
            col_count = max(len(row) for row in table_data)
            col_widths = [17*cm / col_count] * col_count

            pdf_table = Table(table_data, colWidths=col_widths)
            pdf_table.setStyle(TableStyle([
                ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 11),  # Header row
                ('FONT', (0, 1), (-1, -1), 'Helvetica', 10),      # Body rows
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#2c3e50')),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#bdc3c7')),
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#ecf0f1')),  # Header background
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 8),
                ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ]))

            return pdf_table

        except Exception as e:
            # If table parsing fails, return None
            return None

    def _format_json_data(self, data: Any, level: int = 0) -> list:
        """
        Format JSON/dict data into readable PDF elements.

        Args:
            data: JSON data (dict, list, or primitive)
            level: Indentation level for nested data

        Returns:
            List of ReportLab flowables
        """
        elements = []
        indent = level * 0.5 * cm

        if isinstance(data, dict):
            # Create table for key-value pairs
            table_data = []
            for key, value in data.items():
                if isinstance(value, (dict, list)):
                    # Nested structure - display key and recurse
                    elements.append(Paragraph(
                        f"<b>{key}:</b>",
                        self.styles['SubHeading']
                    ))
                    elements.extend(self._format_json_data(value, level + 1))
                else:
                    # Simple key-value pair
                    table_data.append([str(key), str(value)])

            if table_data:
                # Create table for simple key-value pairs
                result_table = Table(table_data, colWidths=[5*cm, 12*cm])
                result_table.setStyle(TableStyle([
                    ('FONT', (0, 0), (0, -1), 'Helvetica-Bold', 11),
                    ('FONT', (1, 0), (1, -1), 'Helvetica', 11),
                    ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#2c3e50')),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#bdc3c7')),
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 8),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                    ('TOPPADDING', (0, 0), (-1, -1), 6),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#ecf0f1')),
                ]))
                elements.append(result_table)
                elements.append(Spacer(1, 0.5*cm))

        elif isinstance(data, list):
            for i, item in enumerate(data):
                elements.append(Paragraph(
                    f"<b>Item {i + 1}:</b>",
                    self.styles['CustomBodyText']
                ))
                elements.extend(self._format_json_data(item, level + 1))
                elements.append(Spacer(1, 0.3*cm))

        else:
            # Primitive value
            elements.append(Paragraph(str(data), self.styles['CustomBodyText']))

        return elements


# Singleton instance
pdf_generator = PDFReportGenerator()
