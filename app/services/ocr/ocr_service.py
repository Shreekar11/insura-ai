"""OCR service for document text extraction and processing."""

import time
from typing import Dict, Any

from app.repositories.ocr_repository import OCRRepository
from app.services.ocr.ocr_base import BaseOCRService, OCRResult
from app.services.normalization.normalization_service import NormalizationService
from app.utils.exceptions import (
    OCRExtractionError,
    OCRTimeoutError,
    InvalidDocumentError,
    APIClientError,
)
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class OCRService(BaseOCRService):
    """OCR service implementation for extracting text from documents.

    This service orchestrates the OCR extraction process using the Mistral API
    and includes comprehensive text normalization for insurance documents.
    It handles business logic, validation, and coordinates between the repository
    layer and the API endpoints.

    Attributes:
        repository: OCR repository for external interactions
        normalization_service: Service for normalizing OCR text
        model: Model name to use for OCR
    """

    def __init__(
        self,
        api_key: str,
        openrouter_api_key: str,
        api_url: str = "https://api.mistral.ai/v1/ocr",
        model: str = "mistral-ocr-latest",
        openrouter_api_url: str = "https://openrouter.ai/api/v1/ocr",
        openrouter_model: str = "mistral-medium-2508",
        timeout: int = 120,
        max_retries: int = 3,
        retry_delay: int = 2,
        use_hybrid_normalization: bool = True,
    ):
        """Initialize OCR service.

        Args:
            api_key: Mistral API key
            openrouter_api_key: OpenRouter API key for LLM normalization
            api_url: Mistral API endpoint URL
            model: Model name to use
            openrouter_api_url: OpenRouter API endpoint URL
            openrouter_model: OpenRouter model name for normalization
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
            retry_delay: Delay between retries in seconds
            use_hybrid_normalization: Use hybrid LLM + code normalization (default: True)
        """
        self.model = model
        self.repository = OCRRepository(
            api_key=api_key,
            api_url=api_url,
            timeout=timeout,
            max_retries=max_retries,
            retry_delay=retry_delay,
        )
        self.normalization_service = NormalizationService(
            openrouter_api_key=openrouter_api_key,
            openrouter_api_url=openrouter_api_url,
            openrouter_model=openrouter_model,
            use_hybrid=use_hybrid_normalization,
        )

        LOGGER.info(
            "Initialized OCR service",
            extra={
                "model": self.model,
                "service_name": self.get_service_name(),
                "use_hybrid_normalization": use_hybrid_normalization,
            },
        )

    async def extract_text_from_url(
        self,
        document_url: str,
        normalize: bool = True
    ) -> OCRResult:
        """Extract text from a document URL using OCR.

        This method orchestrates the complete OCR extraction process:
        1. Validates the document URL
        2. Downloads the document (via repository)
        3. Calls Mistral OCR API (via repository)
        4. Normalizes the extracted text (optional)
        5. Processes and returns the result

        Args:
            document_url: Public URL of the document to process
            normalize: Whether to apply text normalization (default: True)

        Returns:
            OCRResult: Extracted text and metadata

        Raises:
            OCRExtractionError: If extraction fails
            OCRTimeoutError: If processing times out
            InvalidDocumentError: If document is invalid
        """
        LOGGER.info("Starting OCR extraction", extra={"document_url": document_url})
        start_time = time.time()

        try:
            # Validate document URL
            self._validate_document_url(document_url)

            # Download document (validation check)
            await self.repository.download_document(document_url)

            # Extract text using Mistral API
            # extracted_text = await self.repository.call_mistral_ocr_api(
            #     document_url=document_url,
            #     model=self.model,
            # )

            extracted_text = "# PRIVATE CAR LONG TERM PACKAGE POLICY POLICY WORDING \n\n## PREAMBLE\n\nWhereas the Insured by a proposal and declaration dated as stated in the Schedule which shall be the basis of this contract and is deemed to be incorporated herein has applied to SBI GENERAL INSURANCE COMPANY LIMITED (hereinafter called \"the Company\") for the insurance hereinafter contained and has paid the premium mentioned in the Schedule as consideration for such Insurance to the Company and which has been realized by the Company in respect of accidental loss or damage occurring during the Policy Period as stated in the schedule.\nThe term private car shall include Private Car Type Vehicles used for social, domestic and pleasure purposes and also for professional purposes (excluding the carriage of goods other than samples) of the insured or used by the insured's employees for such purposes but excluding use for hire or reward, racing, pacemaking, reliability trial, speed testing and usefor any purposein connection with the Motor Trade.\n\n## NOW THIS POLICY WITNESSETH:\n\nThat subject to the terms, exceptions and conditions contained herein or endorsed or expressed hereon;\n\n## DEFINITIONS\n\n1. Act means the Insurance Act, 1938 (4 of 1938).\n2. Authority means the Insurance Regulatory and Development Authority of India established under the provisions of section 3 of the Insurance Regulatory and Development Authority Act, 1999 (41 of 1999).\n3. Battery Electric Vehicle is a pure/ only or Electric Vehicle, that exclusively uses chemical energy stored in rechargeable battery packs, with no secondary source of propulsion (Eg: Hydrogen fuel cells, internal combustion etc.) Battery Electric vehicle derive all power from battery packs and thus have no internal combustion engine/fuel tank.\n4. Constructive Total Loss - The vehicle be considered to be Constructive Total Loss (CTL), where aggregate cost of retrieval and/ or repair of the vehicle subject to terms and conditions of the Policy exceed $75 \\%$ of the Sum Insured.\n5. Carry Forward means the limit that has been made available from the expired Policy of the Insured with the Company.\n6. Cyber Incident means any malicious act or malware occurring on Insured's personal devices.\n7. Competent Authority means\nI. Chairperson, or\nII. such whole-time member or such committee of the wholetime members or such officer(s) of the Authority, as may be determined by the Chairperson.\n8. Complaint or Grievance means written expression (includes communication in the form of electronic mail or voice based electronic scripts) of dissatisfaction by a complainant with respect to solicitation or sale or purchase of an insurance policy or related services by insurer and /or by distribution channel.\nExplanation: An inquiry or service request would not fall within the definition of the \"complaint\" or \"grievance\".\n9. Complainant means a policyholder or prospect or nominee or assignee or any beneficiary of an insurance policy who has filed a complaint or grievance against an insurer and /or distribution channel.\n10. Cover means an insurance contract whether in the form of a policy document or a cover note or a Certificate of Insurance or any other form as may be specified to evidence the existence of an insurance contract.\n11. Data means any digital information, irrespective of the way it is used, stored, or displayed (such as text, figures, images, video, recordings, or software).\n12. Distribution Channels include insurance agents, intermediaries or insurance intermediaries, and any persons or entities authorised by the Authority to involve in sale and service of insurance policies.\n13. Electric Vehicle is a vehicle that uses one or more electric motors for propulsion, it can be powered by a collector system with electricity from extra vehicular sources, or it can be powered autonomously by a battery. Sometimes charged by solar panels, or by converting fuel to electricity using fuel cells or a generator. Electric Vehicle means, either Battery Electric Vehicle or Hybrid Electric Vehicle.\n\n## Explanation:\n\n(i) \"Material Information\" for the purpose of these regulations shall mean all important, essential and relevant information and documents explicitly sought by insurer in the proposal form.\n(ii) The requirements of \"disclosure of material information\" regarding a proposal or policy, apply both to the insurer and the prospect, under these regulations.\nExplanation: Insurance product referred herein shall also include the riders or add-on(s), if any Where a rider or add-on is tied to a base policy, all the terms and conditions of the rider or add-on shall be mentioned in the prospectus. Where a standalone rider or add-on is offered to a base product, a reference to the rider or add-on shall be made in the prospectus of the base policy indicating the nature of benefits flowing thereupon.\n14. Grace Period means the number of days available with the Insured to opt for Top Up after the expiry of the opted kilometers at the time of inception of the Policy or last Top Up, during the Policy Period/Year.\n15. Hybrid Electric Vehicle is powered by an internal combustion by one or more electric motors, which uses energy stored in the batteries. A hybrid electric vehicle cannot be plugged in to charge the battery. Instead, the battery is charged through regenerative break-in and by the internal combustion engine.\n16. Home-maker shall also be incapacitated to perform Normal Domestic duties and the student shall also be incapacitated to perform Normal Activity of a student.\n17. Lost or Stolen - means having being inadvertently lost or having been stolen by a third party without Insured's assistance, consent or co-operation.\n18. Loss with regard to:\na) toe, finger, thumb means actual complete severance from the foot or hand;\nb) hearing means entire and irrecoverable loss of hearing.\n19. Malware means any unauthorised or illegal Software or code (such as viruses, spyware, computer worms, trojan horses,\n\nrootkits, ransomware, keyloggers, dialers, and rogue security Software) designed to cause harm to or to gain access to or disrupt Personal Devices or computer networks.\n20. Mis-selling includes sale or solicitation of policies by the insurer or through distribution channels, directly or indirectly by\ni. exercising undue influence, use of dominant position or otherwise, or\nii. making a false or misleading statement or misrepresenting the facts or benefits, or\niii. concealing or omitting facts, features, benefits, exclusions with respect to products, or\niv. not taking reasonable care to ensure suitability of the policy to the prospects/policyholders.\n21. Normal Domestic duties means the domestic duties normally performed by a person who remains at home and is not working in regular employment for income, including: cleaning the home, doing the washing, shopping for food, cooking meals; and when applicable, looking after children.\n22. Normal Activity of a student means , activities normally performed by a student and is not working in regular employment for income, including attending any sort of educational institution including vocational training institutions, or studying at home.\n23. Permanent Total Disablement means : the Insured Person is incapacitated due to the injury - for a period lasting 12 months and at the expiry of that period being beyond reasonable hope of improvement - to an extent that engaging in each and every occupation or employment for compensation or profit which he/she was performing just prior to the accident, and for which the Insured Person is reasonably qualified by education \\& training or experience, is not possible for the rest of his/her life.\nIf such Insured Person is either a Home-maker or Student or any Person without any known source of income, then such Permanent Total Disablement shall mean the Insured Person is incapacitated due to the injury - for a period lasting 12 months and at the expiry of that period being beyond reasonable hope of improvement - to an extent that engaging in each and every activity which he/she was performing or was capable to perform just prior to the accident, including future employment for compensation or profit for which the Insured Person is reasonably qualified by education, training or experience, is not possible for the rest of his/her life.\n24. Period of Confinement - means a period of consecutive Days of confinement as an Inpatient caused by an Accident or Injury.\n25. Personal Devices means any devices not limited to tablets, mobile phones, Smart watch used for the purpose of creating, accessing, processing, protecting, monitoring, storing, retrieving, displaying, or transmitting Data.\n26. Proposal form means a form to be filled in by the prospect in physical or electronic form, for furnishing the information including material information, if any, as required by the insurer in respect of a risk, in order to enable the insurer to take informed decision in the context of underwriting the risk, and in the event of acceptance of the risk, to determine the rates, advantages, terms and conditions of the cover to be granted.\n27. Prospect means any person who is a potential customer and likely to enter into an insurance contract either directly with the insurer or through the distribution channel involved.\n28. Prospectus means a document either in physical or electronic format issued by the insurer to sell or promote the insurance product.\n29. Software means any digital standard, customised or individual developed program, or application held or run by a Personal Device that comprises a set of instructions that are capable, when incorporated in a machine readable medium, of causing a machine with information processing capabilities to indicate, perform or achieve a particular function, task or result.\n30. Solicitation means the act of approaching a prospect or a policyholder by an insurer or by a distribution channel with a view to persuading the prospect or a policyholder to purchase or to renew an insurance policy.\n31. Salvage means the value of a vehicle that has met with an accident and has been damaged to such an extent that it no longer makes economic sense to repair\n32. Top Up means the limit that has been opted and paid for during the Policy Period/Year\n33. Un-named Passenger - means a person or persons travelling by the insured vehicle, who is/are neither the Owner Driver of the insured vehicle or its Paid Driver. The number of such Un-named Passengers covered under this Add On Cover should be equal to the Registered Carrying Capacity of the insured vehicle\n34. Unfair trade practice shall have the meaning ascribed to such term in the Consumer Protection Act, 2019, as amended from time to time.\n\n## SECTION I\n\n## ACCIDENTAL LOSS OF OR DAMAGE TO THE VEHICLE INSURED\n\n1. The Company will indemnify the insured against accidental loss or damage to the vehicle insured hereunder and / or its accessories whilst thereon\ni. by fire, explosion, self-ignition or lightning;\nii. by burglary, housebreaking or theft;\niii. by riot and strike;\niv. by earthquake (fire and shock damage);\nv. by flood, typhoon, hurricane, storm, tempest, inundation, cyclone, hailstorm and frost;\nvi. by accidental external means;\nvii. by malicious act;\nviii. by terrorist activity;\nix. whilst in transit by road, rail, inland-waterway, lift, elevator or air;\nx. By landslide and rockslide\n\nSubject to a deduction for depreciation at the rates mentioned below in respect of parts of the vehicle replaced:\n(1) For all rubber/ nylon / plastic parts, tyres and tubes, batteries and airbags- 50\\%\n(2) For fibre glass components-30\\%\n(3) For all parts made of glass - Nil\n(4) Rate of depreciation for all other parts including wooden parts will be as per the following schedule.\n(5) Rate of Depreciation for Painting: In the case of painting, the depreciation rate of $50 \\%$ shall be applied only on the\n\n|  AGE OF VEHICLE | \\% OF\nDEPRECIATION  |\n| --- | --- |\n|  Not exceeding 6 months | Nil  |\n|  Exceeding 6 months but not exceeding 1 year | $5 \\%$  |\n|  Exceeding 1 year but not exceeding 2 years | $10 \\%$  |\n|  Exceeding 2 years but not exceeding 3 years | $15 \\%$  |\n|  Exceeding 3 years but not exceeding 4 years | $25 \\%$  |\n|  Exceeding 4 years but not exceeding 5 years | $35 \\%$  |\n|  Exceeding 5 year but not exceeding 10 years | $40 \\%$  |\n|  Exceeding 10 years | $50 \\%$  |\n\nmaterial cost of total painting charges. In case of a consolidated bill for painting charges, the material component shall be considered as $25 \\%$ of total painting charges for the purpose of applying the depreciation. 2. The Company shall notbeliable to make any payment in respect of: (a) consequential loss, depreciation, wear and tear, mechanical or electrical breakdown, failures or breakages; (b) Damage to tyres and tubes unless the vehicle is damaged at the same time in which case the liability of the Company shall be limited to $50 \\%$ of the cost of replacement. And (c) Any accidental loss or damage suffered to the vehicle whilst the insured or any person driving the vehicle with the knowledge and consent of the insured is under the influence of intoxicating liquor or drugs or driving the insured vehicle without a valid license in accordance with the provisions of Rule 3 of the Central Motor Vehicles Rules,1989(as amended). 3. In the event of the vehicle being disabled by reason of accidental loss or damage covered under this policy the Company will bear the reasonable cost of protection and removal of the vehicle to the nearest repairer and for re-delivery of the vehicle to the insured but not exceeding in all Rs. 1500/- in respect of any one accident. The insured may authorize the repair of the vehicle necessitated by loss or damage covered under this policy for which the Company may be liable under this policy provided that: (a) the estimated cost of such repairs, including replacements, if any, does not exceed Rs. 500; (b) the Company is furnished forthwith with a detailed estimate of the cost of repairs; and (c) The insured shall give the Company every assistance to see that such repair is necessary, and the charges are reasonable.\n\n## SUMINSURED-INSURED'S DECLARED VALUE (IDV)\n\nThe Insured's Declared Value (IDV) of the insured vehicle will be deemed to be the 'SUMINSURED' for the purpose of this policy which is fixed at the commencement of each Policy Period for the insured vehicle. The IDV of the vehicle (and side car/accessories if any fitted to the vehicle) is to be fixed on the basis of the manufacturer's listed selling price of the brand and model of the vehicle insured at the commencement of insurance/renewal and adjusted for depreciation (as per schedule below).\n\nThe schedule of age-wise depreciation as shown below is applicable for the purpose of total loss/constructive total Loss (TL/CTL) claims only.\n\n## THE SCHEDULE OF DEPRECIATION FOR FIXING IDV OF THE VEHICLE\n\n|  AGE OF THE VEHICLE | \\% OF\nDEPRECIATION\nFOR FIXING IDV  |\n| --- | --- |\n|  Not exceeding 6 months | $5 \\%$  |\n|  Exceeding 6 months but not exceeding 1 year | $15 \\%$  |\n|  Exceeding 1 year but not exceeding 2 years | $20 \\%$  |\n|  Exceeding 2 years but not exceeding 3 years | $30 \\%$  |\n|  Exceeding 3 years but not exceeding 4 years | $40 \\%$  |\n|  Exceeding 4 years but not exceeding 5 years | $50 \\%$  |\n\nDV of vehicles beyond 5 years of age and of obsolete models of the vehicles (i.e. models which the manufacturers have discontinued to manufacture) is to be determined on the basis of an understanding between the Company and the Insured. IDV as stated in the Schedule separately for each year of the Policy Period shall be treated as the 'Market Value' of the vehicle throughout the Policy Period without any further depreciation for the purpose of Total Loss (TL) / Constructive Total Loss (CTL) claims. The insured vehicle shall be treated as a CTL if the aggregate cost of retrieval and / or repair of the vehicle, subject to terms and conditions of the policy, exceeds $75 \\%$ of the IDV of the vehicle.\n\n## SECTION II\n\n## LIABILITY TO THIRD PARTIES\n\n1. Subject to the limits of liability as laid down in the Schedule hereto the Company will indemnify the insured in the event of an accident caused by or arising out of the use of the insured vehicle against all sums which the Insured shall become legally liable to pay in respect of :- i) death of or bodily injury to any person including occupants carried in the vehicle (provided such occupants are not carried for hire or reward) but except so far as it is necessary to meet the requirements of Motor Vehicles Act, the Company shall not be liable where such death or injury arises out of and in course of employment of such person by the Insured. ii) damage to any property other than the property belonging to the insured or held in trust or in the custody or control of the insured\n2. The Company will indemnify all costs and expenses incurred by the insured under this Section only with the prior written consent of the Company.\n3. In terms of and subject to the limitations of the indemnity granted by this Section to the insured, the Company will indemnify any driver who is driving the insured vehicle on the insured's order or with the insured's permission provided that such driver shall as though he/she was the insured, observes, fulfill and be subject to the terms, exceptions and conditions of this policy in so far as they apply.\n4. In the event of the death of any person entitled to indemnity under this Policy, the Company will, in respect of the liability\n\nincurred by such person, indemnify his/her personal representative or the legal heir in terms of and subject to the limitations of this policy provided that such personal representative shall prove to the satisfaction of the Company that he/she is the personal representative or the legal heir of the insured and as though such representative or legal heir was the insured and observes, fulfill and be subject to the terms, exceptions and conditions of this policy in so far as they apply. 5. The Company may at its own option: a. arranges for representation at any inquest or fatal inquiry in respect of any death which may be the subject of indemnity under this policy. and b. undertakes the defense of proceedings in any Court of Law in respect of any act or alleged offence causing or relating to any event which may be the subject of indemnity under this policy.\n\n## AVOIDANCE OF CERTAIN TERMS AND RIGHT OF RECOVERY\n\nNothing in this policy or any endorsement hereon shall affect the right of any person indemnified by this policy or any other person, to recover an amount under or by virtue of the provisions of the Motor Vehicles Act.\n\nBut the insured shall repay to the Company all sums paid by the Company which the Company would not have been liable to pay but for the said provisions of the Motor Vehicles Act.\n\n## APPLICATION OF LIMITS OF INDEMNITY\n\nIn the event of any accident involving indemnity to more than one person, any limitation by the terms of this policy and/or of any Endorsement thereon of the amount of any indemnity shall apply to the aggregate amount of indemnity to all persons indemnified and such indemnity shall apply in priority to the insured.\n\n## SECTION III\n\n## PERSONAL ACCIDENT COVER FOR OWNER-DRIVER\n\nSubject otherwise to the terms, exceptions, conditions and limitations of this Policy, the Company undertakes to pay compensation as per the following scale, for bodily injury/ death sustained by the owner-driver of the insured vehicle, whilst the owner-driver was mounting into/dismounting from the insured vehicle or traveling in it as a co-driver, caused by violent accidental external and visible means which independent of any other cause shall within six calendar months of such injury result in:\n\n|  Nature of injury | Scale of\ncompensation  |\n| --- | --- |\n|  (i) Death | $100 \\%$  |\n|  (ii) Loss of two limbs or sight of two eyes or\none limb and sight of one eye | $100 \\%$  |\n|  (iii) Loss of one limb or sight of one eye | $50 \\%$  |\n|  (iv) Permanent total disablement from injuries\nother than named above | $100 \\%$  |\n\nProvided always that: A. compensation shall be payable under only one of the items (i) to (iv) above in respect of the owner-driver of the insured vehicle arising out of any one occurrence and the total liability of the Company shall not in the aggregate exceed the sum of Rs. 15 lakh during the the Policy Period B. no compensation shall be payable in respect of death or bodily injury directly or indirectly wholly or in part arising or resulting from or traceable to (1) intentional self injury suicide or attempted suicide physical defect or infirmity or (2) an accident happening whilst such person has consumed alcohol or is under the influence of intoxicating liquor or drugs. C. Such compensation shall be payable directly to the insured or to his/her legal representatives whose receipt shall be the full discharge in respect of the injury to the Insured.\n\n## This cover is subject to\n\n(a) the owner-driver is the registered owner of the vehicle insured herein; (b) the owner-driver is the Insured named in this Policy. (c) the owner-driver holds a valid driving license, in accordance with the provisions of Rule 3 of the Central Motor Vehicles Rules, 1989(as amended), at the time of the accident.\n\n## GENERAL EXCEPTIONS - Applicable to all Sections of the Policy\n\nThe Company shall not be liable under this Policy in respect of\n\n1. Any accidental loss damage and/or liability caused, sustained, or incurred outside the Geographical Area as stated in the Schedule.\n2. Any claim arising out of any contractual liability.\n3. Any accidental loss/damage and/or liability caused, sustained or incurred whilst the vehicle insured herein is (a) being used otherwise than in accordance with the 'Limitations as to Use' as stated in the Schedule or (b) being driven by or is for the purpose of being driven by or in the charge of any person other than a driver as stated in the Driver's Clause mentioned in the Schedule.\n4. (a) any accidental loss or damage to any property whatsoever or any loss or expense whatsoever resulting or arising there from or any consequential loss. (b) any liability of whatsoever nature directly or indirectly caused by or contributed to by or arising from ionizing radiations or contamination by radioactivity from any nuclear fuel or from any nuclear waste from the combustion of nuclear fuel. For the purpose of this exception combustion shall include any self-sustaining process of nuclear fission.\n5. Any accidental loss or damage or liability directly or indirectly caused by or contributed to by or arising from nuclear weapons material.\n6. Any accidental loss damage and/or liability directly or indirectly or proximately or remotely occasioned by or contributed to by or traceable to or arising out of or in connection with war, invasion, the act of foreign enemies, hostilities or warlike operations (whether before or after declaration of war) civil war, mutiny rebellion, military or usurped power or by any direct or indirect consequence of any of the said occurrences and in the event of any claim hereunder the Insured shall prove that the accidental loss damage and/or liability arose independently of and was in no way connected with or occasioned by or contributed to by or traceable to any of the said occurrences or any consequences thereof and in default of such proof, the Company shall not be liable to make any payment in respect of such a claim.\n7. The Policy does not cover any accidental loss or damage caused to the Insured vehicle caused by or arising from or aggravated by" 

            # Validate extraction result
            self._validate_extraction_result(extracted_text, document_url)

            # Normalize text if requested
            normalized_text = extracted_text
            normalization_applied = False
            
            if normalize:
                LOGGER.info("Applying text normalization")
                normalized_text = await self.normalization_service.normalize_text(
                    extracted_text
                )
                normalization_applied = True
                
                LOGGER.info(
                    "Text normalization completed",
                    extra={
                        "original_length": len(extracted_text),
                        "normalized_length": len(normalized_text),
                    }
                )

            # Write normalized text to file
            try:
                with open("normalized_text_llm.txt", "w", encoding="utf-8") as f:
                    f.write(normalized_text)
                LOGGER.info("Normalized text written to normalized_text.txt")
            except Exception as e:
                LOGGER.error(f"Failed to write normalized text to file: {str(e)}")

            # Calculate processing time
            processing_time = time.time() - start_time

            # Create OCR result
            result = self._create_ocr_result(
                raw_text=extracted_text,
                normalized_text=normalized_text,
                document_url=document_url,
                processing_time=processing_time,
                normalization_applied=normalization_applied,
            )

            LOGGER.info(
                "OCR extraction completed successfully",
                extra={
                    "document_url": document_url,
                    "raw_text_length": len(extracted_text),
                    "normalized_text_length": len(normalized_text),
                    "processing_time": processing_time,
                    "normalization_applied": normalization_applied,
                },
            )

            return result

        except (InvalidDocumentError, APIClientError, OCRTimeoutError):
            # Re-raise known exceptions
            raise

        except Exception as e:
            LOGGER.error(
                "OCR extraction failed",
                exc_info=True,
                extra={"document_url": document_url, "error": str(e)},
            )
            raise OCRExtractionError(f"Failed to extract text from document: {str(e)}") from e

    def _validate_document_url(self, document_url: str) -> None:
        """Validate document URL format.

        Args:
            document_url: URL to validate

        Raises:
            InvalidDocumentError: If URL is invalid
        """
        if not document_url:
            raise InvalidDocumentError("Document URL cannot be empty")

        if not document_url.startswith(("http://", "https://")):
            raise InvalidDocumentError("Document URL must start with http:// or https://")

        LOGGER.debug("Document URL validated", extra={"document_url": document_url})

    def _validate_extraction_result(self, extracted_text: str, document_url: str) -> None:
        """Validate OCR extraction result.

        Args:
            extracted_text: Extracted text to validate
            document_url: Document URL being processed

        Raises:
            OCRExtractionError: If extraction result is invalid
        """
        if not extracted_text:
            LOGGER.warning(
                "OCR extraction returned empty text",
                extra={"document_url": document_url},
            )
            raise OCRExtractionError("OCR extraction returned empty text")

        if len(extracted_text.strip()) < 10:
            LOGGER.warning(
                "OCR extraction returned suspiciously short text",
                extra={
                    "document_url": document_url,
                    "text_length": len(extracted_text),
                },
            )

        LOGGER.debug(
            "Extraction result validated",
            extra={
                "document_url": document_url,
                "text_length": len(extracted_text),
            },
        )

    def _create_ocr_result(
        self,
        raw_text: str,
        normalized_text: str,
        document_url: str,
        processing_time: float,
        normalization_applied: bool,
    ) -> OCRResult:
        """Create OCR result object with metadata.

        Args:
            raw_text: Raw extracted text content
            normalized_text: Normalized text content
            document_url: Source document URL
            processing_time: Time taken for processing in seconds
            normalization_applied: Whether normalization was applied

        Returns:
            OCRResult: Complete OCR result with metadata
        """
        # Use normalized text as the primary text output
        final_text = normalized_text if normalization_applied else raw_text
        
        return OCRResult(
            text=final_text,
            confidence=0.95,  # Mistral typically has high confidence
            metadata={
                "service": self.get_service_name(),
                "model": self.model,
                "processing_time_seconds": round(processing_time, 2),
                "document_url": document_url,
                "raw_text_length": len(raw_text),
                "normalized_text_length": len(normalized_text),
                "text_length": len(final_text),
                "word_count": len(final_text.split()),
                "normalization_applied": normalization_applied,
                "text_reduction_percent": round(
                    (1 - len(normalized_text) / len(raw_text)) * 100, 2
                ) if normalization_applied else 0.0,
            },
        )

    def get_service_name(self) -> str:
        """Get the name of the OCR service.

        Returns:
            str: Service name
        """
        return "Mistral OCR"

    async def normalize_text(self, text: str) -> str:
        """Normalize OCR text for better processing.

        This method provides direct access to the normalization service
        for cases where text has already been extracted and needs to be
        normalized separately.

        Args:
            text: Raw OCR text to normalize

        Returns:
            str: Normalized text
            
        Example:
            >>> service = OCRService(api_key="...")
            >>> raw_text = "PoIicy Number: 12345\\nPage 1 of 5"
            >>> normalized = await service.normalize_text(raw_text)
            >>> print(normalized)
            Policy Number: 12345
        """
        return self.normalization_service.normalize_text(text)
    
    async def normalize_page_text(
        self,
        page_text: str,
        page_number: int
    ) -> Dict[str, Any]:
        """Normalize text from a single page.

        This method is useful for page-level processing and debugging.
        It provides detailed metadata about the normalization process.

        Args:
            page_text: Raw text from a single page
            page_number: Page number for logging

        Returns:
            dict: Dictionary containing normalized text and metadata
            
        Example:
            >>> service = OCRService(api_key="...")
            >>> result = await service.normalize_page_text(page_text, 1)
            >>> print(result["normalized_text"])
        """
        return self.normalization_service.normalize_page_text(
            page_text=page_text,
            page_number=page_number,
        )
    
    async def detect_document_sections(self, text: str) -> Dict[str, list]:
        """Detect common insurance document sections.

        This method identifies key sections in insurance documents which
        can be useful for downstream classification and extraction.

        Args:
            text: Normalized document text

        Returns:
            dict: Dictionary mapping section names to line numbers where found
            
        Example:
            >>> service = OCRService(api_key="...")
            >>> sections = await service.detect_document_sections(text)
            >>> print(sections)
            {'declarations': [1, 5], 'coverages': [10, 15]}
        """
        return self.normalization_service.detect_document_sections(text)
