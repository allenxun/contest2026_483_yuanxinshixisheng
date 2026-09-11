package cn.yuanxin.mvp.web.identity;

/**
 * 服务端派生的可靠成员身份引用（对应 T01 members 的
 * identity_namespace + face_subject_ref）。仅内部使用，绝不回给客户端。
 */
public record ResolvedFaceIdentity(String identityNamespace, String faceSubjectRef) {
}
