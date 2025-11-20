"""Simple test script to verify chunking implementation.

This script tests the chunking service with sample insurance document text.
"""

import asyncio
from app.services.chunking import ChunkingService, TokenCounter


async def test_chunking():
    """Test the chunking service with sample text."""
    
    # Sample insurance document text (simulating a large document)
    sample_text = """
# PRIVATE CAR LONG TERM PACKAGE POLICY POLICY WORDING

## PREAMBLE

Whereas the Insured by a proposal and declaration dated as stated in the Schedule which shall be the basis of this contract and is deemed to be incorporated herein has applied to SBI GENERAL INSURANCE COMPANY LIMITED (hereinafter called "the Company") for the insurance hereinafter contained and has paid the premium mentioned in the Schedule as consideration for such Insurance to the Company and which has been realized by the Company in respect of accidental loss or damage occurring during the Policy Period as stated in the schedule.

The term private car shall include Private Car Type Vehicles used for social, domestic and pleasure purposes and also for professional purposes (excluding the carriage of goods other than samples) of the insured or used by the insured's employees for such purposes but excluding use for hire or reward, racing, pacemaking, reliability trial, speed testing and usefor any purposein connection with the Motor Trade.

## NOW THIS POLICY WITNESSETH:

That subject to the terms, exceptions and conditions contained herein or endorsed or expressed hereon;

## DEFINITIONS

1. Act means the Insurance Act, 1938 (4 of 1938).
2. Authority means the Insurance Regulatory and Development Authority of India established under the provisions of section 3 of the Insurance Regulatory and Development Authority Act, 1999 (41 of 1999).
3. Battery Electric Vehicle is a pure/ only or Electric Vehicle, that exclusively uses chemical energy stored in rechargeable battery packs, with no secondary source of propulsion (Eg: Hydrogen fuel cells, internal combustion etc.) Battery Electric vehicle derive all power from battery packs and thus have no internal combustion engine/fuel tank.
4. Constructive Total Loss - The vehicle be considered to be Constructive Total Loss (CTL), where aggregate cost of retrieval and/ or repair of the vehicle subject to terms and conditions of the Policy exceed 75% of the Sum Insured.

## SECTION I

## ACCIDENTAL LOSS OF OR DAMAGE TO THE VEHICLE INSURED

1. The Company will indemnify the insured against accidental loss or damage to the vehicle insured hereunder and / or its accessories whilst thereon
i. by fire, explosion, self-ignition or lightning;
ii. by burglary, housebreaking or theft;
iii. by riot and strike;
iv. by earthquake (fire and shock damage);
v. by flood, typhoon, hurricane, storm, tempest, inundation, cyclone, hailstorm and frost;
vi. by accidental external means;
vii. by malicious act;
viii. by terrorist activity;
ix. whilst in transit by road, rail, inland-waterway, lift, elevator or air;
x. By landslide and rockslide

Subject to a deduction for depreciation at the rates mentioned below in respect of parts of the vehicle replaced:
(1) For all rubber/ nylon / plastic parts, tyres and tubes, batteries and airbags- 50%
(2) For fibre glass components-30%
(3) For all parts made of glass - Nil
(4) Rate of depreciation for all other parts including wooden parts will be as per the following schedule.

## SECTION II

## LIABILITY TO THIRD PARTIES

1. Subject to the limits of liability as laid down in the Schedule hereto the Company will indemnify the insured in the event of an accident caused by or arising out of the use of the insured vehicle against all sums which the Insured shall become legally liable to pay in respect of :- 
i) death of or bodily injury to any person including occupants carried in the vehicle (provided such occupants are not carried for hire or reward) but except so far as it is necessary to meet the requirements of Motor Vehicles Act, the Company shall not be liable where such death or injury arises out of and in course of employment of such person by the Insured. 
ii) damage to any property other than the property belonging to the insured or held in trust or in the custody or control of the insured

## SECTION III

## PERSONAL ACCIDENT COVER FOR OWNER-DRIVER

Subject otherwise to the terms, exceptions, conditions and limitations of this Policy, the Company undertakes to pay compensation as per the following scale, for bodily injury/ death sustained by the owner-driver of the insured vehicle, whilst the owner-driver was mounting into/dismounting from the insured vehicle or traveling in it as a co-driver, caused by violent accidental external and visible means which independent of any other cause shall within six calendar months of such injury result in:

| Nature of injury | Scale of compensation |
| --- | --- |
| (i) Death | 100% |
| (ii) Loss of two limbs or sight of two eyes or one limb and sight of one eye | 100% |
| (iii) Loss of one limb or sight of one eye | 50% |
| (iv) Permanent total disablement from injuries other than named above | 100% |

Provided always that: 
A. compensation shall be payable under only one of the items (i) to (iv) above in respect of the owner-driver of the insured vehicle arising out of any one occurrence and the total liability of the Company shall not in the aggregate exceed the sum of Rs. 15 lakh during the the Policy Period 
B. no compensation shall be payable in respect of death or bodily injury directly or indirectly wholly or in part arising or resulting from or traceable to (1) intentional self injury suicide or attempted suicide physical defect or infirmity or (2) an accident happening whilst such person has consumed alcohol or is under the influence of intoxicating liquor or drugs.
"""
    
    print("=" * 80)
    print("CHUNKING SERVICE TEST")
    print("=" * 80)
    
    # Initialize services
    token_counter = TokenCounter()
    chunking_service = ChunkingService(
        max_tokens_per_chunk=1500,
        overlap_tokens=50,
        enable_section_chunking=True
    )
    
    # Count tokens in sample text
    total_tokens = token_counter.count_tokens(sample_text)
    print(f"\nSample text statistics:")
    print(f"  Total characters: {len(sample_text)}")
    print(f"  Total words: {len(sample_text.split())}")
    print(f"  Estimated tokens: {total_tokens}")
    
    # Chunk the document
    print(f"\nChunking document...")
    chunks = chunking_service.chunk_document(sample_text)
    
    # Get statistics
    stats = chunking_service.get_chunk_statistics(chunks)
    
    print(f"\nChunking results:")
    print(f"  Total chunks: {stats['total_chunks']}")
    print(f"  Total tokens: {stats['total_tokens']}")
    print(f"  Avg tokens per chunk: {stats['avg_tokens_per_chunk']:.1f}")
    print(f"  Max tokens in chunk: {stats['max_tokens']}")
    print(f"  Min tokens in chunk: {stats['min_tokens']}")
    print(f"  Pages detected: {stats['pages']}")
    print(f"  Sections detected: {stats['sections']}")
    
    # Display chunk details
    print(f"\nChunk details:")
    print("-" * 80)
    for i, chunk in enumerate(chunks, 1):
        print(f"\nChunk {i}:")
        print(f"  Page: {chunk.metadata.page_number}")
        print(f"  Section: {chunk.metadata.section_name or 'N/A'}")
        print(f"  Chunk index: {chunk.metadata.chunk_index}")
        print(f"  Token count: {chunk.metadata.token_count}")
        print(f"  Text preview: {chunk.text[:100]}...")
    
    # Test merging
    print(f"\n" + "=" * 80)
    print("Testing chunk merging...")
    merged_text = chunking_service.merge_chunks(chunks, add_section_markers=True)
    print(f"Merged text length: {len(merged_text)} characters")
    print(f"Merged text preview (first 500 chars):")
    print("-" * 80)
    print(merged_text[:500])
    print("...")
    
    print(f"\n" + "=" * 80)
    print("✓ Chunking service test completed successfully!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_chunking())
