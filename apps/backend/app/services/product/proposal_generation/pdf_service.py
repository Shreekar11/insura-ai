"""Service for generating PDF documents for insurance proposals using fpdf2."""

import os
from io import BytesIO
from datetime import datetime
from fpdf import FPDF
from app.schemas.product.proposal_generation import Proposal
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)

class PDFProposalService:
    """Service to generate professional PDF from Proposal object using fpdf2."""

    def __init__(self):
        pass

    def generate_pdf(self, proposal: Proposal) -> BytesIO:
        """Generate PDF and return as byte stream."""
        try:
            pdf = FPDF(orientation="landscape", unit="mm", format="A4")
            pdf.set_auto_page_break(auto=True, margin=15)
            
            # --- 1. Cover Page ---
            pdf.add_page()
            
            # Broker Logo (if exists)
            if proposal.broker_logo_path and os.path.exists(proposal.broker_logo_path):
                # Try to place logo in top center
                pdf.image(proposal.broker_logo_path, x=110, y=30, w=70)
            
            pdf.set_y(80)
            pdf.set_font("helvetica", "B", 32)
            pdf.set_text_color(0, 51, 102) # #003366
            pdf.cell(0, 20, "INSURANCE PROPOSAL", ln=True, align="C")
            
            pdf.set_y(110)
            pdf.set_font("helvetica", "", 18)
            pdf.set_text_color(85, 85, 85) # #555555
            pdf.cell(0, 10, f"{proposal.policy_type}", ln=True, align="C")
            pdf.set_font("helvetica", "B", 20)
            pdf.cell(0, 15, f"{proposal.insured_name}", ln=True, align="C")
            
            pdf.set_y(160)
            pdf.set_font("helvetica", "", 12)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(0, 10, f"Prepared by: {proposal.broker_name}", ln=True, align="C")
            pdf.cell(0, 10, f"Date: {datetime.now().strftime('%B %d, %Y')}", ln=True, align="C")

            # --- 2. Executive Summary ---
            pdf.add_page()
            pdf.set_font("helvetica", "B", 18)
            pdf.set_text_color(0, 51, 102)
            pdf.cell(0, 15, "EXECUTIVE SUMMARY", ln=True)
            pdf.line(pdf.get_x(), pdf.get_y(), 280, pdf.get_y())
            pdf.ln(10)
            
            pdf.set_font("helvetica", "", 11)
            pdf.set_text_color(68, 68, 68) # #444444
            pdf.multi_cell(0, 8, proposal.executive_summary, align="J")

            # --- 3. Comparison Matrix ---
            pdf.add_page()
            pdf.set_font("helvetica", "B", 18)
            pdf.set_text_color(0, 51, 102)
            pdf.cell(0, 15, "COMPARISON MATRIX", ln=True)
            pdf.line(pdf.get_x(), pdf.get_y(), 280, pdf.get_y())
            pdf.ln(10)

            # Table Header
            renewal_ids = []
            for row in proposal.comparison_table:
                for rid in row.renewal_values.keys():
                    if rid not in renewal_ids:
                        renewal_ids.append(rid)
            renewal_ids = renewal_ids[:3]
            
            col_widths = [80, 50] + [40] * len(renewal_ids) + [30]
            
            pdf.set_font("helvetica", "B", 9)
            pdf.set_fill_color(0, 51, 102)
            pdf.set_text_color(255, 255, 255)
            
            headers = ["Coverage / Provision", "Expiring Policy"] + [f"Quote {i+1}" for i in range(len(renewal_ids))] + ["Insight"]
            for i, h in enumerate(headers):
                pdf.cell(col_widths[i], 10, h, border=1, align="C", fill=True)
            pdf.ln()

            # Table Rows
            pdf.set_text_color(51, 51, 51)
            pdf.set_font("helvetica", "", 8)
            for row in proposal.comparison_table:
                # Calculate required height for multi_cell
                label = f"{row.category}: {row.label}"
                
                # Use multi_cell for first column to wrap text
                x_start = pdf.get_x()
                y_start = pdf.get_y()
                pdf.set_font("helvetica", "B", 8)
                pdf.multi_cell(col_widths[0], 6, label, border=1, align="L")
                h = pdf.get_y() - y_start
                
                # Fill other cells in same row
                pdf.set_y(y_start)
                pdf.set_x(x_start + col_widths[0])
                pdf.set_font("helvetica", "", 8)
                pdf.cell(col_widths[1], h, row.expiring_value or "N/A", border=1, align="C")
                
                for i, rid in enumerate(renewal_ids):
                    pdf.cell(col_widths[2+i], h, row.renewal_values.get(rid, "N/A"), border=1, align="C")
                
                # Delta flag with color
                flag = row.delta_flag or "NEUTRAL"
                if flag == "POSITIVE":
                    pdf.set_fill_color(230, 255, 250) # light teal
                    pdf.set_text_color(44, 122, 123)
                elif flag == "NEGATIVE":
                    pdf.set_fill_color(255, 245, 245) # light red
                    pdf.set_text_color(197, 48, 48)
                else:
                    pdf.set_fill_color(255, 255, 255)
                    pdf.set_text_color(113, 128, 150)
                
                pdf.cell(col_widths[-1], h, flag, border=1, align="C", fill=True)
                pdf.ln(h)
                pdf.set_text_color(51, 51, 51)

            # --- 4. Premium Summary ---
            if proposal.premium_summary:
                pdf.add_page()
                pdf.set_font("helvetica", "B", 18)
                pdf.set_text_color(0, 51, 102)
                pdf.cell(0, 15, "PREMIUM SUMMARY", ln=True)
                pdf.line(pdf.get_x(), pdf.get_y(), 280, pdf.get_y())
                pdf.ln(10)
                
                sum_widths = [100, 60, 60, 60]
                pdf.set_font("helvetica", "B", 10)
                pdf.set_fill_color(45, 55, 72)
                pdf.set_text_color(255, 255, 255)
                headers = ["Carrier", "Total Premium", "Terms", "Binding Deadline"]
                for i, h in enumerate(headers):
                    pdf.cell(sum_widths[i], 10, h, border=1, align="C", fill=True)
                pdf.ln()
                
                pdf.set_text_color(51, 51, 51)
                pdf.set_font("helvetica", "", 9)
                for p in proposal.premium_summary:
                    pdf.cell(sum_widths[0], 10, p.carrier, border=1, align="L")
                    pdf.cell(sum_widths[1], 10, p.total_premium, border=1, align="C")
                    pdf.cell(sum_widths[2], 10, p.terms, border=1, align="C")
                    pdf.cell(sum_widths[3], 10, p.binding_deadline, border=1, align="C")
                    pdf.ln()

            # --- 5. Signatures ---
            pdf.add_page()
            pdf.set_font("helvetica", "B", 18)
            pdf.set_text_color(0, 51, 102)
            pdf.cell(0, 15, "NEXT STEPS & DISCLAIMERS", ln=True)
            pdf.line(pdf.get_x(), pdf.get_y(), 280, pdf.get_y())
            pdf.ln(10)
            
            pdf.set_font("helvetica", "", 10)
            pdf.set_text_color(51, 51, 51)
            pdf.multi_cell(0, 8, "To bind coverage, please sign below and return this document to your broker by the binding deadline.")
            pdf.ln(10)
            
            pdf.set_fill_color(248, 250, 252)
            pdf.set_font("helvetica", "B", 9)
            pdf.cell(0, 8, "Disclaimers:", ln=True, fill=True)
            pdf.set_font("helvetica", "", 9)
            pdf.set_text_color(100, 116, 139)
            disclaimers_list = proposal.disclaimers or ["This proposal is for informational purposes only. Actual coverage is dictated by the policy terms and conditions issued by the carrier. Please review all documents carefully."]
            disclaimers_text = "\n".join(disclaimers_list) if isinstance(disclaimers_list, list) else disclaimers_list
            pdf.multi_cell(0, 6, disclaimers_text, border=1, fill=True)
            
            pdf.ln(40)
            y_sig = pdf.get_y()
            
            # Signature Lines
            pdf.line(20, y_sig, 100, y_sig)
            pdf.set_xy(20, y_sig + 2)
            pdf.set_font("helvetica", "B", 10)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(80, 5, "Client Signature", ln=True)
            pdf.set_font("helvetica", "", 9)
            pdf.cell(80, 5, "Date")
            
            pdf.line(180, y_sig, 260, y_sig)
            pdf.set_xy(180, y_sig + 2)
            pdf.set_font("helvetica", "B", 10)
            pdf.cell(80, 5, "Broker Representative", ln=True)
            pdf.set_font("helvetica", "", 9)
            pdf.cell(80, 5, proposal.broker_name)

            buffer = BytesIO()
            pdf.output(buffer)
            buffer.seek(0)
            
            LOGGER.info(f"Generated PDF for proposal {proposal.proposal_id} using fpdf2")
            return buffer
            
        except Exception as e:
            LOGGER.error(f"Failed to generate PDF with fpdf2: {str(e)}")
            raise
