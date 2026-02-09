"""
INTEGRATION GUIDE - How to Wire V2 Modules into Existing System

This guide shows the exact code changes needed to integrate the new V2 modules
into the existing matcher.py and verifier.py files.

IMPORTANT: This is a GRADUAL migration. V1 modules remain untouched.
You can run V2 alongside V1 for A/B testing.
"""

# =============================================================================
# STEP 1: Update matcher.py - Add V2 Imports
# =============================================================================

# At the top of matcher.py, add these imports:

from app.verifier.enhanced_matcher import (
    prefilter_item,
    validate_hard_constraints,
    calculate_hybrid_score_v3,
    calibrate_confidence,
    get_category_config,
    MatchDecision
)
from app.verifier.medical_core_extractor_v2 import extract_medical_core_v2
from app.verifier.smart_normalizer import normalize_with_weights
from app.verifier.failure_reasons_v2 import (
    determine_failure_reason_v2,
    FailureReasonV2
)


# =============================================================================
# STEP 2: Update ItemMatch Dataclass
# =============================================================================

# In matcher.py, update the ItemMatch dataclass to include new fields:

@dataclass
class ItemMatch:
    """Result of item matching."""
    matched_text: Optional[str]
    similarity: float
    index: int
    item: Optional[Dict[str, Any]]
    normalized_item_name: Optional[str] = None
    
    # V2 ENHANCEMENTS
    failure_reason_v2: Optional[FailureReasonV2] = None
    failure_explanation: Optional[str] = None
    score_breakdown: Optional[Dict] = None
    medical_metadata: Optional[Dict] = None
    confidence_decision: Optional[MatchDecision] = None


# =============================================================================
# STEP 3: Create match_item_v2() Method
# =============================================================================

# In SemanticMatcher class, add this new method:

def match_item_v2(
    self,
    item_name: str,
    hospital_name: str,
    category_name: str,
    threshold: float = None,  # Will be overridden by category config
    use_llm: bool = True,
) -> ItemMatch:
    """
    Enhanced item matching with V2 architecture.
    
    Implements 6-layer matching:
    0. Pre-filtering
    1. Medical core extraction
    2. Hard constraint validation
    3. Semantic matching
    4. Hybrid re-ranking
    5. Confidence calibration
    6. Failure reason determination
    """
    
    # =========================================================================
    # LAYER 0: Pre-Filtering
    # =========================================================================
    
    should_skip, skip_reason = prefilter_item(item_name)
    if should_skip:
        logger.info(f"Pre-filtered item: '{item_name}' (reason: {skip_reason})")
        return ItemMatch(
            matched_text=None,
            similarity=0.0,
            index=-1,
            item=None,
            normalized_item_name=item_name,
            failure_reason_v2=FailureReasonV2.ADMIN_CHARGE if skip_reason == "ARTIFACT" else FailureReasonV2.PACKAGE_ONLY,
            failure_explanation=f"Pre-filtered: {skip_reason}"
        )
    
    # =========================================================================
    # LAYER 1: Medical Core Extraction
    # =========================================================================
    
    bill_result = extract_medical_core_v2(item_name)
    logger.debug(f"Extracted medical core: '{bill_result.core_text}' from '{item_name}'")
    
    # Get category-specific configuration
    config = get_category_config(category_name)
    category_threshold = config.semantic_threshold
    
    # =========================================================================
    # LAYER 3: Semantic Matching (using existing FAISS logic)
    # =========================================================================
    
    # Get hospital and category indices (existing logic)
    hospital_match = self.match_hospital(hospital_name)
    if hospital_match.index == -1:
        return ItemMatch(
            matched_text=None,
            similarity=0.0,
            index=-1,
            item=None,
            normalized_item_name=bill_result.core_text,
            failure_reason_v2=FailureReasonV2.NOT_IN_TIEUP,
            failure_explanation="Hospital not found in tie-up data"
        )
    
    category_match = self.match_category(category_name, hospital_match.index)
    if category_match.index == -1:
        return ItemMatch(
            matched_text=None,
            similarity=0.0,
            index=-1,
            item=None,
            normalized_item_name=bill_result.core_text,
            failure_reason_v2=FailureReasonV2.NOT_IN_TIEUP,
            failure_explanation=f"Category '{category_name}' not found in hospital tie-up"
        )
    
    # Get item index for this category
    item_index = self.get_item_index(hospital_match.index, category_match.index)
    if item_index is None or item_index.size == 0:
        return ItemMatch(
            matched_text=None,
            similarity=0.0,
            index=-1,
            item=None,
            normalized_item_name=bill_result.core_text,
            failure_reason_v2=FailureReasonV2.NOT_IN_TIEUP,
            failure_explanation=f"No items found in category '{category_name}'"
        )
    
    # Get top-K candidates (increased from 3 to 5 for better re-ranking)
    k = min(5, item_index.size)
    query_embedding = self.get_embedding(bill_result.core_text)
    results = item_index.search(query_embedding, k=k)
    
    distances = results['distances'][0]
    indices = results['indices'][0]
    
    # =========================================================================
    # LAYER 2 & 4: Validate Constraints + Hybrid Re-Ranking
    # =========================================================================
    
    best_candidate = None
    best_score = 0.0
    best_breakdown = None
    best_tieup_result = None
    
    for i, (distance, idx) in enumerate(zip(distances, indices)):
        if idx == -1:
            continue
        
        # Get candidate item
        candidate_item = self.get_item_by_index(
            hospital_match.index,
            category_match.index,
            int(idx)
        )
        
        if not candidate_item:
            continue
        
        candidate_name = candidate_item.get('item_name', '')
        semantic_similarity = 1.0 - distance
        
        # Extract medical core from candidate
        tieup_result = extract_medical_core_v2(candidate_name)
        
        # LAYER 2: Validate hard constraints
        valid, constraint_reason = validate_hard_constraints(
            bill_metadata={
                'dosage': bill_result.dosage,
                'form': bill_result.form,
                'modality': bill_result.modality,
                'body_part': bill_result.body_part,
                'core_text': bill_result.core_text,
            },
            tieup_metadata={
                'dosage': tieup_result.dosage,
                'form': tieup_result.form,
                'modality': tieup_result.modality,
                'body_part': tieup_result.body_part,
                'core_text': tieup_result.core_text,
            },
            bill_category=category_name,
            tieup_category=category_name,  # Same category for now
            config=config
        )
        
        if not valid:
            logger.debug(f"Candidate '{candidate_name}' failed hard constraints: {constraint_reason}")
            # Track this for failure reason if it's the best semantic match
            if i == 0:  # First candidate (best semantic match)
                best_candidate = candidate_name
                best_tieup_result = tieup_result
                # Extract specific failure reason from constraint_reason
                if "DOSAGE_MISMATCH" in constraint_reason:
                    failure_reason = FailureReasonV2.DOSAGE_MISMATCH
                elif "FORM_MISMATCH" in constraint_reason:
                    failure_reason = FailureReasonV2.FORM_MISMATCH
                elif "CATEGORY_BOUNDARY" in constraint_reason:
                    failure_reason = FailureReasonV2.WRONG_CATEGORY
                elif "MODALITY_MISMATCH" in constraint_reason:
                    failure_reason = FailureReasonV2.MODALITY_MISMATCH
                elif "BODYPART_MISMATCH" in constraint_reason:
                    failure_reason = FailureReasonV2.BODYPART_MISMATCH
                else:
                    failure_reason = FailureReasonV2.LOW_SIMILARITY
                
                return ItemMatch(
                    matched_text=candidate_name,
                    similarity=semantic_similarity,
                    index=-1,
                    item=None,
                    normalized_item_name=bill_result.core_text,
                    failure_reason_v2=failure_reason,
                    failure_explanation=constraint_reason
                )
            continue
        
        # LAYER 4: Calculate hybrid score
        final_score, breakdown = calculate_hybrid_score_v3(
            bill_text=bill_result.core_text,
            tieup_text=tieup_result.core_text,
            semantic_similarity=semantic_similarity,
            bill_metadata={
                'dosage': bill_result.dosage,
                'form': bill_result.form,
                'modality': bill_result.modality,
                'body_part': bill_result.body_part,
            },
            tieup_metadata={
                'dosage': tieup_result.dosage,
                'form': tieup_result.form,
                'modality': tieup_result.modality,
                'body_part': tieup_result.body_part,
            },
            category=category_name
        )
        
        logger.debug(f"Candidate '{candidate_name}': semantic={semantic_similarity:.3f}, hybrid={final_score:.3f}")
        
        # Track best candidate
        if final_score > best_score:
            best_score = final_score
            best_candidate = candidate_name
            best_breakdown = breakdown
            best_tieup_result = tieup_result
            best_item = candidate_item
            best_idx = int(idx)
    
    # =========================================================================
    # LAYER 5: Confidence Calibration
    # =========================================================================
    
    if best_candidate:
        decision, calibrated_confidence = calibrate_confidence(
            best_score, category_name, best_breakdown
        )
        
        logger.info(f"Best match: '{best_candidate}' (score={best_score:.3f}, decision={decision.value})")
        
        if decision == MatchDecision.AUTO_MATCH:
            # Accept match
            return ItemMatch(
                matched_text=best_candidate,
                similarity=calibrated_confidence,
                index=best_idx,
                item=best_item,
                normalized_item_name=bill_result.core_text,
                score_breakdown=best_breakdown,
                medical_metadata={
                    'bill': {
                        'dosage': bill_result.dosage,
                        'form': bill_result.form,
                        'modality': bill_result.modality,
                        'body_part': bill_result.body_part,
                    },
                    'tieup': {
                        'dosage': best_tieup_result.dosage,
                        'form': best_tieup_result.form,
                        'modality': best_tieup_result.modality,
                        'body_part': best_tieup_result.body_part,
                    }
                },
                confidence_decision=decision
            )
        
        elif decision == MatchDecision.LLM_VERIFY and use_llm:
            # Use LLM verification (existing logic)
            from app.verifier.llm_router import verify_match_with_llm
            
            llm_result = verify_match_with_llm(
                bill_item=bill_result.core_text,
                tieup_item=best_tieup_result.core_text,
                similarity=best_score
            )
            
            if llm_result.get('match', False):
                return ItemMatch(
                    matched_text=best_candidate,
                    similarity=calibrated_confidence,
                    index=best_idx,
                    item=best_item,
                    normalized_item_name=bill_result.core_text,
                    score_breakdown=best_breakdown,
                    confidence_decision=decision
                )
    
    # =========================================================================
    # LAYER 6: Failure Reason Determination
    # =========================================================================
    
    reason, explanation = determine_failure_reason_v2(
        item_name=item_name,
        normalized_name=bill_result.core_text,
        category=category_name,
        best_candidate=best_candidate,
        best_similarity=best_score if best_candidate else 0.0,
        bill_metadata={
            'dosage': bill_result.dosage,
            'form': bill_result.form,
            'modality': bill_result.modality,
            'body_part': bill_result.body_part,
        } if bill_result else None,
        tieup_metadata={
            'dosage': best_tieup_result.dosage if best_tieup_result else None,
            'form': best_tieup_result.form if best_tieup_result else None,
            'modality': best_tieup_result.modality if best_tieup_result else None,
            'body_part': best_tieup_result.body_part if best_tieup_result else None,
        } if best_tieup_result else None,
        threshold=category_threshold
    )
    
    return ItemMatch(
        matched_text=best_candidate,
        similarity=best_score if best_candidate else 0.0,
        index=-1,
        item=None,
        normalized_item_name=bill_result.core_text,
        failure_reason_v2=reason,
        failure_explanation=explanation,
        score_breakdown=best_breakdown
    )


# =============================================================================
# STEP 4: Update verifier.py to Use V2
# =============================================================================

# In verifier.py, update the verify_bill() method to use match_item_v2:

def verify_bill_v2(self, bill_data: Dict, hospital_name: str) -> Dict:
    """Enhanced bill verification using V2 matching."""
    
    results = []
    
    for item in bill_data.get('items', []):
        item_name = item.get('item_name', '')
        category = item.get('category', 'Unknown')
        bill_amount = item.get('amount', 0.0)
        
        # Use V2 matcher
        match_result = self.matcher.match_item_v2(
            item_name=item_name,
            hospital_name=hospital_name,
            category_name=category,
            use_llm=True
        )
        
        # Build result with V2 fields
        result = {
            'bill_item': item_name,
            'category': category,
            'bill_amount': bill_amount,
            'matched_item': match_result.matched_text,
            'similarity': match_result.similarity,
        }
        
        # Add V2 enhancements
        if match_result.score_breakdown:
            result['score_breakdown'] = match_result.score_breakdown
        
        if match_result.medical_metadata:
            result['medical_metadata'] = match_result.medical_metadata
        
        if match_result.confidence_decision:
            result['confidence_decision'] = match_result.confidence_decision.value
        
        # Determine status
        if match_result.index != -1:
            # Matched
            allowed_amount = match_result.item.get('rate', 0.0)
            result['status'] = 'GREEN' if bill_amount <= allowed_amount else 'RED'
            result['allowed_amount'] = allowed_amount
            result['extra_amount'] = max(0, bill_amount - allowed_amount)
        else:
            # Not matched
            result['status'] = 'MISMATCH'
            result['failure_reason'] = match_result.failure_reason_v2.value if match_result.failure_reason_v2 else 'UNKNOWN'
            result['failure_explanation'] = match_result.failure_explanation
        
        results.append(result)
    
    return {
        'results': results,
        'summary': self._calculate_summary_v2(results)
    }


def _calculate_summary_v2(self, results: List[Dict]) -> Dict:
    """Calculate summary with V2 failure reason breakdown."""
    
    summary = {
        'total_items': len(results),
        'green': sum(1 for r in results if r['status'] == 'GREEN'),
        'red': sum(1 for r in results if r['status'] == 'RED'),
        'mismatch': sum(1 for r in results if r['status'] == 'MISMATCH'),
        'total_bill_amount': sum(r['bill_amount'] for r in results),
        'total_allowed_amount': sum(r.get('allowed_amount', 0) for r in results),
        'total_extra_amount': sum(r.get('extra_amount', 0) for r in results),
    }
    
    # V2: Breakdown of mismatch reasons
    mismatch_breakdown = {}
    for r in results:
        if r['status'] == 'MISMATCH':
            reason = r.get('failure_reason', 'UNKNOWN')
            mismatch_breakdown[reason] = mismatch_breakdown.get(reason, 0) + 1
    
    summary['mismatch_breakdown'] = mismatch_breakdown
    
    return summary


# =============================================================================
# STEP 5: Testing
# =============================================================================

# To test the V2 implementation:

if __name__ == "__main__":
    # Initialize matcher
    from app.verifier.matcher import SemanticMatcher
    
    matcher = SemanticMatcher()
    
    # Test cases
    test_items = [
        ("(30049099) NICORANDIL-TABLET-5MG |GTF", "Narayana Hospital", "Medicines"),
        ("CONSULTATION - FIRST VISIT", "Narayana Hospital", "Procedures"),
        ("MRI BRAIN", "Narayana Hospital", "Diagnostics"),
        ("For queries call 1800-XXX-XXXX", "Narayana Hospital", "Unknown"),
    ]
    
    print("=" * 80)
    print("V2 MATCHER TEST RESULTS")
    print("=" * 80)
    
    for item_name, hospital, category in test_items:
        print(f"\nTesting: '{item_name}'")
        print(f"Category: {category}")
        print("-" * 80)
        
        result = matcher.match_item_v2(item_name, hospital, category)
        
        print(f"Matched: {result.matched_text}")
        print(f"Similarity: {result.similarity:.3f}")
        print(f"Status: {'MATCH' if result.index != -1 else 'MISMATCH'}")
        
        if result.failure_reason_v2:
            print(f"Failure Reason: {result.failure_reason_v2.value}")
            print(f"Explanation: {result.failure_explanation}")
        
        if result.score_breakdown:
            print(f"Score Breakdown: {result.score_breakdown}")
        
        print("-" * 80)


print("""
================================================================================
INTEGRATION COMPLETE
================================================================================

Next Steps:
1. Run the test code above to verify V2 works
2. Compare V1 vs V2 outputs on sample bills
3. Gradually migrate endpoints to use verify_bill_v2()
4. Monitor performance and accuracy
5. Fine-tune category thresholds based on results

Rollback Plan:
- If issues arise, simply use match_item() instead of match_item_v2()
- V1 code remains untouched and functional
- No database migrations required
================================================================================
""")
