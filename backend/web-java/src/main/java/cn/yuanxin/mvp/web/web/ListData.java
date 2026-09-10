package cn.yuanxin.mvp.web.web;

import java.util.List;

/**
 * 列表响应 data 形状（契约 ListData）：{@code {items, nextCursor}}。
 * nextCursor 为 null 表示无后续页（字段保留，不省略）。
 */
public record ListData<T>(List<T> items, String nextCursor) {
}
