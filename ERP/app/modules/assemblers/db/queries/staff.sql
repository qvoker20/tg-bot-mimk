-- Staff query module.
-- Keep staff roster and permission mappings here.
--
-- Recommended objects:
-- 1) view for active workers by subdivision
-- 2) indexes for fast worker lookup by source_user_id and subdivision

CREATE INDEX IF NOT EXISTS idx_assemblers_staff_source_user_id
ON assemblers_staff (source_user_id);

CREATE INDEX IF NOT EXISTS idx_assemblers_staff_subdivision
ON assemblers_staff (subdivision);
