"""Service for generating PDF documents for insurance proposals using WeasyPrint and Jinja2."""

import os
from io import BytesIO
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML
from app.schemas.product.proposal_generation import Proposal
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)

class PDFProposalService:
    """Service to generate professional PDF from Proposal object using WeasyPrint."""

    def __init__(self):
        # Setup Jinja2 environment
        template_dir = os.path.join(os.path.dirname(__file__), "templates")
        self.jinja_env = Environment(loader=FileSystemLoader(template_dir))

    def generate_pdf(self, proposal: Proposal) -> BytesIO:
        """Generate PDF and return as byte stream."""
        try:
            # 1. Prepare template data
            template = self.jinja_env.get_template("proposal.html")
            
            # Identify all unique renewal IDs for the matrix columns
            renewal_ids = []
            for row in proposal.comparison_table:
                for rid in row.renewal_values.keys():
                    if rid not in renewal_ids:
                        renewal_ids.append(rid)
            
            # Limit to 3 for readability in landscape
            renewal_ids = renewal_ids[:3]
            
            html_content = template.render(
                proposal=proposal,
                renewal_ids=renewal_ids,
                now=datetime.now()
            )

            # 2. Render PDF using WeasyPrint
            buffer = BytesIO()
            # Note: WeasyPrint expects absolute paths for local files in HTML (if any)
            # or we can pass a base_url
            HTML(string=html_content, base_url=os.getcwd()).write_pdf(target=buffer)
            
            buffer.seek(0)
            LOGGER.info(f"Generated PDF for proposal {proposal.proposal_id} using WeasyPrint")
            return buffer
            
        except Exception as e:
            LOGGER.error(f"Failed to generate PDF with WeasyPrint: {str(e)}")
            # Fallback or re-raise
            raise
