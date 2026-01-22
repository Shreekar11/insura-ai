"""Service for generating PDF documents for insurance proposals."""

from fpdf import FPDF
from io import BytesIO
from typing import Optional
from app.schemas.product.proposal import Proposal
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)

class PDFProposalGenerator(FPDF):
    """Custom FPDF class for branded proposals."""
    
    def header(self):
        """Add branded header."""
        self.set_font("helvetica", "B", 10)
        self.set_text_color(100, 100, 100)
        self.cell(0, 10, "INSURA AI - BROKER PROPOSAL", 0, 1, "R")
        self.ln(5)

    def footer(self):
        """Add page footer."""
        self.set_y(-15)
        self.set_font("helvetica", "I", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", 0, 0, "C")

class PDFProposalService:
    """Service to generate professional PDF from Proposal object."""

    def generate_pdf(self, proposal: Proposal) -> BytesIO:
        """Generate PDF and return as byte stream."""
        pdf = PDFProposalGenerator()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        
        # 1. Cover Page
        self._add_cover_page(pdf, proposal)
        
        # 2. Executive Summary
        pdf.add_page()
        self._add_section_header(pdf, "EXECUTIVE SUMMARY")
        pdf.set_font("helvetica", "", 11)
        pdf.multi_cell(0, 7, proposal.executive_summary)
        pdf.ln(10)

        # 3. Comparison Table
        self._add_section_header(pdf, "SUMMARY COMPARISON")
        self._add_comparison_table(pdf, proposal)
        
        # 4. Detailed Sections
        for section in proposal.sections:
            pdf.add_page()
            self._add_section_header(pdf, section.title.upper())
            pdf.set_font("helvetica", "", 11)
            pdf.multi_cell(0, 7, section.narrative)
            pdf.ln(10)
            
            if section.key_findings:
                pdf.set_font("helvetica", "B", 11)
                pdf.cell(0, 10, "Key Findings:", 0, 1)
                pdf.set_font("helvetica", "", 10)
                for finding in section.key_findings:
                    bullet = f"- {finding['delta']}: {finding['field']}"
                    if finding.get('coverage'):
                        bullet += f" ({finding['coverage']})"
                    pdf.cell(0, 7, bullet, 0, 1)

        # Output to buffer
        buffer = BytesIO()
        pdf.output(buffer)
        buffer.seek(0)
        return buffer

    def _add_cover_page(self, pdf: FPDF, proposal: Proposal):
        """Design the cover page."""
        pdf.set_y(60)
        pdf.set_font("helvetica", "B", 26)
        pdf.set_text_color(0, 51, 102) # Dark Blue
        pdf.cell(0, 20, "Insurance Policy Proposal", 0, 1, "C")
        
        pdf.set_y(100)
        pdf.set_font("helvetica", "B", 16)
        pdf.set_text_color(50, 50, 50)
        pdf.cell(0, 10, f"Prepared for: {proposal.insured_name}", 0, 1, "C")
        
        pdf.ln(10)
        pdf.set_font("helvetica", "", 12)
        pdf.cell(0, 10, f"Policy Type: {proposal.policy_type}", 0, 1, "C")
        pdf.cell(0, 10, f"Proposed Carrier: {proposal.carrier_name}", 0, 1, "C")
        
        pdf.set_y(220)
        pdf.set_font("helvetica", "I", 10)
        pdf.cell(0, 10, f"Generated on: {proposal.created_at.strftime('%B %d, %Y')}", 0, 1, "C")

    def _add_section_header(self, pdf: FPDF, title: str):
        """Add a consistent section header."""
        pdf.set_font("helvetica", "B", 14)
        pdf.set_fill_color(240, 240, 240)
        pdf.set_text_color(0, 51, 102)
        pdf.cell(0, 12, title, 0, 1, "L", fill=True)
        pdf.ln(5)

    def _add_comparison_table(self, pdf: FPDF, proposal: Proposal):
        """Add a detailed comparison table."""
        pdf.set_font("helvetica", "B", 9)
        pdf.set_fill_color(0, 51, 102)
        pdf.set_text_color(255, 255, 255)
        
        # Headers
        col_widths = [40, 40, 40, 40, 30]
        headers = ["Category/Field", "Expiring", "Renewal", "Delta Type", "Status"]
        
        for i, header in enumerate(headers):
            pdf.cell(col_widths[i], 10, header, 1, 0, "C", fill=True)
        pdf.ln()
        
        # Rows
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("helvetica", "", 8)
        
        for row in proposal.comparison_table:
            # Check for page break
            if pdf.get_y() > 250:
                pdf.add_page()
                # Re-add headers? (Optional)
            
            # Label
            label = row.label[:25] + "..." if len(row.label) > 25 else row.label
            pdf.cell(col_widths[0], 8, f"{row.category}: {label}", 1)
            
            # Values
            pdf.cell(col_widths[1], 8, str(row.expiring_value or "N/A"), 1, 0, "C")
            pdf.cell(col_widths[2], 8, str(row.renewal_value or "N/A"), 1, 0, "C")
            
            # Delta
            pdf.cell(col_widths[3], 8, row.delta_type, 1, 0, "C")
            
            # Flag (Color code)
            if row.delta_flag == "POSITIVE":
                pdf.set_fill_color(204, 255, 204) # Light green
            elif row.delta_flag == "NEGATIVE":
                pdf.set_fill_color(255, 204, 204) # Light red
            else:
                pdf.set_fill_color(255, 255, 255)
                
            pdf.cell(col_widths[4], 8, row.delta_flag, 1, 1, "C", fill=True)
