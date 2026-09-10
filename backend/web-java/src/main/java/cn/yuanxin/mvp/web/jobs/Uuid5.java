package cn.yuanxin.mvp.web.jobs;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.UUID;

/**
 * RFC 4122 UUIDv5（SHA-1）。与 Python uuid.uuid5 字节一致（同一输入字符串）。
 * FIXED_NS 硬编码于 contracts/decisions-notes.md §4（两侧禁止各算各的输入）。
 */
public final class Uuid5 {

    /** uuid5(NAMESPACE_DNS, "contest2026_483_yuanxinshixisheng")（contracts 定稿值）。 */
    public static final UUID FIXED_NS =
            UUID.fromString("f988d041-6031-5120-8075-f90b6b05553e");

    private Uuid5() {
    }

    public static UUID uuid5(UUID namespace, String name) {
        try {
            MessageDigest sha1 = MessageDigest.getInstance("SHA-1");
            sha1.update(toBytes(namespace));
            sha1.update(name.getBytes(StandardCharsets.UTF_8));
            byte[] h = sha1.digest();
            h[6] = (byte) ((h[6] & 0x0f) | 0x50); // version 5
            h[8] = (byte) ((h[8] & 0x3f) | 0x80); // RFC 4122 variant
            return fromBytes(h);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-1 unavailable", e);
        }
    }

    private static byte[] toBytes(UUID uuid) {
        byte[] b = new byte[16];
        long msb = uuid.getMostSignificantBits();
        long lsb = uuid.getLeastSignificantBits();
        for (int i = 0; i < 8; i++) {
            b[i] = (byte) (msb >>> (56 - i * 8));
            b[8 + i] = (byte) (lsb >>> (56 - i * 8));
        }
        return b;
    }

    private static UUID fromBytes(byte[] b) {
        long msb = 0;
        long lsb = 0;
        for (int i = 0; i < 8; i++) msb = (msb << 8) | (b[i] & 0xffL);
        for (int i = 8; i < 16; i++) lsb = (lsb << 8) | (b[i] & 0xffL);
        return new UUID(msb, lsb);
    }
}
