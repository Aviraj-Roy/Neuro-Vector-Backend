"""
Phase-3 Display Formatters for Hospital Bill Verifier.

Provides formatted console output for both views:
1. Debug View - Verbose, detailed trace
2. Final View - Clean, user-friendly report

Both formatters produce human-readable output suitable for logging and reporting.
"""

from __future__ import annotations

import logging
from typing import List

from app.verifier.models import VerificationStatus
from app.verifier.models_v3 import (
    DebugCategoryTrace,
    DebugItemTrace,
    DebugView,
    FinalCategory,
    FinalItem,
    FinalView,
    Phase3Response,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Debug View Formatter (Verbose)
# =============================================================================


def format_debug_item(item: DebugItemTrace, index: int) -> str:
    """
    Format a single debug item trace.
    
    Shows all details including:
    - Original text and normalized form
    - Matching strategy and scores
    - ALL candidates tried (Phase 4-6 enhancement)
    - Best candidate and final result
    - Package information (Phase 4-6 enhancement)
    - Notes and diagnostics
    """
    lines = []
    lines.append(f"\n  [{index}] {item.original_bill_text}")
    lines.append(f"      Normalized: {item.normalized_item_name}")
    lines.append(f"      Bill Amount: ₹{item.bill_amount:.2f}")
    lines.append(f"      Category: {item.detected_category}")
    
    if item.category_attempted != item.detected_category:
        lines.append(f"      Category Attempted: {item.category_attempted} (reconciled)")
    
    lines.append(f"      Matching Strategy: {item.matching_strategy}")
    
    if item.semantic_similarity is not None:
        lines.append(f"      Semantic Similarity: {item.semantic_similarity:.3f}")
    if item.token_overlap is not None:
        lines.append(f"      Token Overlap: {item.token_overlap:.3f}")
    if item.medical_anchor_score is not None:
        lines.append(f"      Medical Anchor Score: {item.medical_anchor_score:.3f}")
    if item.hybrid_score is not None:
        lines.append(f"      Hybrid Score: {item.hybrid_score:.3f}")
    
    # Phase 4-6: Show all candidates tried
    if item.all_candidates_tried:
        lines.append(f"      Candidates Tried ({len(item.all_candidates_tried)}):")
        for idx, candidate in enumerate(item.all_candidates_tried, 1):
            status = "✅ ACCEPTED" if candidate.was_accepted else "❌ REJECTED"
            lines.append(
                f"        {idx}. {candidate.candidate_name} "
                f"(sim={candidate.similarity_score:.3f}) - {status}"
            )
            if candidate.rejection_reason:
                lines.append(f"           Reason: {candidate.rejection_reason}")
    elif item.best_candidate:
        # Fallback to showing best candidate only
        lines.append(f"      Best Candidate: {item.best_candidate} (sim={item.best_candidate_similarity:.3f})")
    
    if item.matched_item:
        lines.append(f"      ✅ Matched: {item.matched_item}")
        if item.allowed_rate:
            lines.append(f"      Allowed Rate: ₹{item.allowed_rate:.2f}")
        lines.append(f"      Allowed Amount: ₹{item.allowed_amount:.2f}")
    
    # Status
    status_emoji = {
        VerificationStatus.GREEN: "✅",
        VerificationStatus.RED: "❌",
        VerificationStatus.MISMATCH: "⚠️",
        VerificationStatus.ALLOWED_NOT_COMPARABLE: "ℹ️",
        VerificationStatus.IGNORED_ARTIFACT: "⚪",
    }
    
    emoji = status_emoji.get(item.final_status, "❓")
    lines.append(f"      Status: {emoji} {item.final_status.value}")
    
    if item.extra_amount > 0:
        lines.append(f"      Extra Amount: ₹{item.extra_amount:.2f}")
    
    if item.failure_reason:
        lines.append(f"      Failure Reason: {item.failure_reason.value}")
    
    # Phase 4-6: Show package information
    if item.is_package_item:
        lines.append(f"      📦 Package Item: Yes")
        if item.package_components:
            lines.append(f"      Package Components: {', '.join(item.package_components)}")
    
    if item.notes:
        for note in item.notes:
            lines.append(f"      Note: {note}")
    
    if item.reconciliation_attempted:
        status = "✅ Succeeded" if item.reconciliation_succeeded else "❌ Failed"
        lines.append(f"      Reconciliation: {status}")
        if item.all_categories_tried:
            lines.append(f"      Categories Tried: {', '.join(item.all_categories_tried)}")
    
    return "\n".join(lines)


def format_debug_category(category: DebugCategoryTrace) -> str:
    """Format a complete debug category trace."""
    lines = []
    lines.append(f"\n{'=' * 80}")
    lines.append(f"CATEGORY: {category.category.upper()}")
    lines.append(f"{'=' * 80}")
    
    for idx, item in enumerate(category.items, 1):
        lines.append(format_debug_item(item, idx))
    
    return "\n".join(lines)


def display_debug_view(debug_view: DebugView) -> None:
    """
    Display complete debug view to console.
    
    Shows full trace with all details for developer inspection.
    """
    print("\n" + "=" * 80)
    print("DEBUG VIEW (Full Trace)")
    print("=" * 80)
    print(f"Hospital: {debug_view.hospital}")
    if debug_view.matched_hospital:
        print(f"Matched Hospital: {debug_view.matched_hospital} (similarity={debug_view.hospital_similarity:.3f})")
    print(f"Total Items Processed: {debug_view.total_items_processed}")
    print("=" * 80)
    
    for category in debug_view.categories:
        print(format_debug_category(category))
    
    print("\n" + "=" * 80)
    print("END DEBUG VIEW")
    print("=" * 80)


# =============================================================================
# Final View Formatter (Clean)
# =============================================================================


def format_final_item(item: FinalItem, index: int) -> str:
    """
    Format a single final item.
    
    Shows only essential information:
    - Display name
    - Status
    - Amounts
    - Reason tag (if MISMATCH)
    """
    status_emoji = {
        VerificationStatus.GREEN: "✅",
        VerificationStatus.RED: "❌",
        VerificationStatus.MISMATCH: "⚠️",
        VerificationStatus.ALLOWED_NOT_COMPARABLE: "ℹ️",
        VerificationStatus.IGNORED_ARTIFACT: "⚪",
    }
    
    emoji = status_emoji.get(item.final_status, "❓")
    
    # Basic line
    line = f"  {index}. {emoji} {item.display_name}"
    line += f" | Bill: ₹{item.bill_amount:.2f}"
    
    if item.final_status == VerificationStatus.GREEN:
        line += f" | Allowed: ₹{item.allowed_amount:.2f}"
    elif item.final_status == VerificationStatus.RED:
        line += f" | Allowed: ₹{item.allowed_amount:.2f} | Extra: ₹{item.extra_amount:.2f}"
    elif item.final_status == VerificationStatus.MISMATCH:
        if item.reason_tag:
            line += f" | Reason: {item.reason_tag.value}"
    elif item.final_status == VerificationStatus.ALLOWED_NOT_COMPARABLE:
        line += " | Not Comparable"
    
    return line


def format_final_category(category: FinalCategory) -> str:
    """Format a complete final category."""
    lines = []
    lines.append(f"\n{'─' * 80}")
    lines.append(f"📁 {category.category.upper()}")
    lines.append(f"{'─' * 80}")
    
    for idx, item in enumerate(category.items, 1):
        lines.append(format_final_item(item, idx))
    
    # Category totals
    lines.append(f"\n  Category Totals:")
    lines.append(f"    Bill: ₹{category.total_bill:.2f}")
    lines.append(f"    Allowed: ₹{category.total_allowed:.2f}")
    if category.total_extra > 0:
        lines.append(f"    Extra: ₹{category.total_extra:.2f}")
    
    return "\n".join(lines)


def display_final_view(final_view: FinalView) -> None:
    """
    Display clean final view to console.
    
    Shows user-friendly report with essential information only.
    """
    print("\n" + "=" * 80)
    print("FINAL VIEW (User Report)")
    print("=" * 80)
    print(f"Hospital: {final_view.hospital}")
    if final_view.matched_hospital:
        print(f"Matched Hospital: {final_view.matched_hospital}")
    print("=" * 80)
    
    for category in final_view.categories:
        print(format_final_category(category))
    
    # Grand totals
    print("\n" + "=" * 80)
    print("GRAND TOTALS")
    print("=" * 80)
    print(f"  Total Bill: ₹{final_view.grand_total_bill:.2f}")
    print(f"  Total Allowed: ₹{final_view.grand_total_allowed:.2f}")
    if final_view.grand_total_extra > 0:
        print(f"  Total Extra: ₹{final_view.grand_total_extra:.2f}")
    
    print(f"\n  Status Summary:")
    print(f"    ✅ GREEN: {final_view.green_count}")
    print(f"    ❌ RED: {final_view.red_count}")
    print(f"    ⚠️ MISMATCH: {final_view.mismatch_count}")
    print(f"    ℹ️ ALLOWED_NOT_COMPARABLE: {final_view.allowed_not_comparable_count}")
    
    print("\n" + "=" * 80)
    print("END FINAL VIEW")
    print("=" * 80)


# =============================================================================
# Phase-3 Display
# =============================================================================


def display_phase3_response(phase3_response: Phase3Response, view: str = "both") -> None:
    """
    Display Phase-3 response.
    
    Args:
        phase3_response: Complete Phase-3 response
        view: Which view to display ("debug", "final", or "both")
    """
    if view in ["debug", "both"]:
        display_debug_view(phase3_response.debug_view)
    
    if view in ["final", "both"]:
        display_final_view(phase3_response.final_view)
    
    # Show consistency check
    if phase3_response.consistency_check:
        print("\n" + "=" * 80)
        print("CONSISTENCY CHECK")
        print("=" * 80)
        for key, value in phase3_response.consistency_check.items():
            emoji = "✅" if value is True else "❌" if value is False else "ℹ️"
            print(f"  {emoji} {key}: {value}")
        print("=" * 80)


# =============================================================================
# Testing
# =============================================================================

if __name__ == "__main__":
    print("Phase-3 display formatters module loaded successfully!")
    print("Use display_phase3_response() to show dual-view output.")
