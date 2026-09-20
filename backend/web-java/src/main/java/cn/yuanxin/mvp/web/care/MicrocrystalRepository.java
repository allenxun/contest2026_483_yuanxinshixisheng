package cn.yuanxin.mvp.web.care;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

/**
 * T04 microcrystals 只读存在性 + 能力投影（单表；{@code capabilities} 以
 * {@code ::text} 取出后由服务层解析）。占用状态不在此表（V1 迁移明确
 * 不新增占用列，占用从 T07 的两个部分唯一索引裁决）。
 */
@Repository
public class MicrocrystalRepository {

    private final JdbcTemplate jdbc;

    public MicrocrystalRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public record MicrocrystalRow(UUID id, String capabilities) {
    }

    private static final String COLUMNS = "id, capabilities::text AS capabilities";

    private static final org.springframework.jdbc.core.RowMapper<MicrocrystalRow> MAPPER =
            (rs, i) -> new MicrocrystalRow(
                    rs.getObject("id", UUID.class),
                    rs.getString("capabilities"));

    public Optional<MicrocrystalRow> findById(UUID microcrystalId) {
        List<MicrocrystalRow> rows = jdbc.query(
                "SELECT " + COLUMNS + " FROM microcrystals WHERE id = ?", MAPPER, microcrystalId);
        return rows.isEmpty() ? Optional.empty() : Optional.of(rows.get(0));
    }

    /** 最终短事务锁序 T04：{@code SELECT ... FOR UPDATE}（锁内复核能力覆盖）。 */
    public Optional<MicrocrystalRow> lockById(UUID microcrystalId) {
        List<MicrocrystalRow> rows = jdbc.query(
                "SELECT " + COLUMNS + " FROM microcrystals WHERE id = ? FOR UPDATE",
                MAPPER, microcrystalId);
        return rows.isEmpty() ? Optional.empty() : Optional.of(rows.get(0));
    }
}
