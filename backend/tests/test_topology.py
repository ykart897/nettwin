from app.database import Base, SessionLocal, engine
from app.models import Asset, AssetRelation
from app.topology import TopologyService


def setup_module():
    Base.metadata.create_all(bind=engine)


def test_topology_keeps_assets_separate_and_links_by_proximity():
    db = SessionLocal()
    try:
        db.query(AssetRelation).delete()
        db.query(Asset).filter(Asset.source.in_(["topology-cell", "topology-agent"])).delete(
            synchronize_session=False
        )
        cell = Asset(
            asset_type="cell_site",
            source="topology-cell",
            external_id="cell-1",
            name="Cell",
            latitude=41.0,
            longitude=29.0,
        )
        agent = Asset(
            asset_type="local_agent",
            source="topology-agent",
            external_id="agent-1",
            name="Agent",
            latitude=41.01,
            longitude=29.01,
        )
        db.add_all([cell, agent])
        db.commit()

        count = TopologyService().rebuild(db)
        relation = (
            db.query(AssetRelation)
            .filter(
                AssetRelation.source_asset_id == cell.id,
                AssetRelation.target_asset_id == agent.id,
            )
            .one()
        )
        assert count >= 1
        assert relation.relation_type == "MEASURED_BY"
        assert 0 < relation.confidence <= 1
    finally:
        db.close()
