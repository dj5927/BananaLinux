from pathlib import Path
import sys
root=Path(sys.argv[1])
p=root/"src/common/drm_display.cpp"
s=p.read_text()
a="if (next_connector && next_connector->connection == DRM_MODE_CONNECTED && next_connector->count_modes > 0)"
b="if (next_connector && next_connector->connection == DRM_MODE_CONNECTED && next_connector->count_modes > 0 &&\n        (HasBananaLease() || !std::getenv(\"BANANA_DUCK_READY_FILE\") ||\n         (next_connector->connector_type == DRM_MODE_CONNECTOR_DSI && next_connector->connector_type_id == 2)))"
c="if (connector_ptr && connector_ptr->connection == DRM_MODE_CONNECTED)"
d="if (connector_ptr && connector_ptr->connection == DRM_MODE_CONNECTED &&\n          (HasBananaLease() || !std::getenv(\"BANANA_DUCK_READY_FILE\") ||\n           (connector_ptr->connector_type == DRM_MODE_CONNECTOR_DSI && connector_ptr->connector_type_id == 2)))"
for x,y in [(a,b),(c,d)]:
    assert s.count(x)==1
    s=s.replace(x,y)
p.write_text(s)
