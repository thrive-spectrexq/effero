"""Fleet coordination package for multi-agent negotiation, auctions, and consensus."""

from __future__ import annotations

from effero.core.fleet.auction import (
    Bid,
    BidRejection,
    BidScorer,
    CallForProposals,
    FailoverManager,
    LeaseManager,
    NodeModality,
    SealedBidAuction,
    TaskAnnouncement,
    TaskAward,
    TaskLease,
)
from effero.core.fleet.coordinator import FleetCoordinator, FleetNode

__all__ = [
    "Bid",
    "BidRejection",
    "BidScorer",
    "CallForProposals",
    "FailoverManager",
    "FleetCoordinator",
    "FleetNode",
    "LeaseManager",
    "NodeModality",
    "SealedBidAuction",
    "TaskAnnouncement",
    "TaskAward",
    "TaskLease",
]
