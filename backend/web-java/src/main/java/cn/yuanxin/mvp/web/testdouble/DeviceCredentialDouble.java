package cn.yuanxin.mvp.web.testdouble;

import cn.yuanxin.mvp.web.auth.DeviceCredentialProvider;
import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;

import java.util.Optional;
import java.util.UUID;

/**
 * 云台设备凭据测试替身（仅 dev/test）：对照 gimbals 行验证
 * auth_subject_ref（= 提交 credential）+ credential_version。
 * 行由测试/种子 SQL 建立（Java 写边界：T03 由 Web 维护）。
 *
 * <p>真实设备签名协议（nonce/proof 算法、密钥预置）由设备团队对接后替换
 * 本替身；proof 在本双中不校验（协议未冻结）。</p>
 */
public class DeviceCredentialDouble implements DeviceCredentialProvider {

    private final JdbcTemplate jdbc;

    public DeviceCredentialDouble(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public Optional<GimbalIdentity> verify(String credential, long credentialVersion, String proof) {
        try {
            var rows = jdbc.query("SELECT id, serial_no, credential_version FROM gimbals"
                            + " WHERE auth_subject_ref = ?",
                    (rs, i) -> new GimbalIdentity(rs.getObject("id", UUID.class),
                            rs.getString("serial_no"), rs.getLong("credential_version")),
                    credential);
            if (rows.isEmpty() || rows.get(0).credentialVersion() != credentialVersion) {
                return Optional.empty(); // 凭据或版本不符：统一失败，不区分（防枚举）
            }
            return Optional.of(rows.get(0));
        } catch (DataAccessException e) {
            return Optional.empty(); // fail closed：DB 异常不登记为可信在线
        }
    }
}
