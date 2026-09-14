from __future__ import annotations

import json
from math import asin, cos, radians, sin, sqrt

from app.models import Asset, AssetRelation


class TopologyService:
    def rebuild(self, db) -> int:
        assets = (
            db.query(Asset)
            .filter(Asset.active == True, Asset.latitude.isnot(None), Asset.longitude.isnot(None))  # noqa: E712
            .all()
        )
        cells = [asset for asset in assets if asset.asset_type == "cell_site"]
        measurement_assets = [asset for asset in assets if asset.asset_type != "cell_site"]
        db.query(AssetRelation).delete()
        relations = []

        neighbor_pairs = set()
        for source in cells:
            neighbors = sorted(
                (
                    (_distance_km(source, target), target)
                    for target in cells
                    if target.id != source.id
                ),
                key=lambda item: (item[0], item[1].id),
            )
            for distance, target in neighbors[:4]:
                pair = tuple(sorted((source.id, target.id)))
                if distance <= 5 and pair not in neighbor_pairs:
                    neighbor_pairs.add(pair)
                    first, second = sorted((source, target), key=lambda item: item.id)
                    relations.append(self._relation(first, second, "NEIGHBOR_OF", distance))

        for measurement in measurement_assets:
            if not cells:
                continue
            distance, cell = min(
                ((_distance_km(measurement, candidate), candidate) for candidate in cells),
                key=lambda item: item[0],
            )
            if distance <= 20:
                confidence = max(0.1, round(1 - distance / 20, 2))
                relations.append(
                    self._relation(
                        cell,
                        measurement,
                        "MEASURED_BY",
                        distance,
                        confidence=confidence,
                    )
                )

        db.add_all(relations)
        db.commit()
        return len(relations)

    def _relation(
        self,
        source: Asset,
        target: Asset,
        relation_type: str,
        distance: float,
        confidence: float | None = None,
    ) -> AssetRelation:
        return AssetRelation(
            source_asset_id=source.id,
            target_asset_id=target.id,
            relation_type=relation_type,
            distance_km=round(distance, 3),
            confidence=confidence,
            metadata_json=json.dumps({"basis": "geographic_proximity"}),
        )


def _distance_km(source: Asset, target: Asset) -> float:
    dlat = radians(target.latitude - source.latitude)
    dlon = radians(target.longitude - source.longitude)
    a = (
        sin(dlat / 2) ** 2
        + cos(radians(source.latitude))
        * cos(radians(target.latitude))
        * sin(dlon / 2) ** 2
    )
    return 6371 * 2 * asin(sqrt(a))
