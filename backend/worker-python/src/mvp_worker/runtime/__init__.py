"""T12 async_jobs 运行时：领取 / 续租 / 过期回收 / 代次受控完成。

至少一次执行（at-least-once），从不宣称 exactly-once；重复落地由
租约代次（lease_revision）+ 领取者（lease_owner）+ 业务 input_revision
的条件更新共同阻断（DD 9.2、ARCH 8.2/8.3）。
"""
