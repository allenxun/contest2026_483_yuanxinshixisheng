package cn.yuanxin.mvp.web.auth;

import cn.yuanxin.mvp.web.error.ApiException;
import cn.yuanxin.mvp.web.error.ErrorCode;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.core.MethodParameter;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.support.WebDataBinderFactory;
import org.springframework.web.context.request.NativeWebRequest;
import org.springframework.web.method.support.HandlerMethodArgumentResolver;
import org.springframework.web.method.support.ModelAndViewContainer;

/**
 * 把 BearerAuthFilter 写入的 {@link PrincipalContext} 解析为控制器方法参数。
 * 公开端点的控制器不得声明该参数；缺失时以 401 防御（理论上不可达——
 * 过滤器已拦截，此处仅为编程错误兜底）。
 */
@Component
public class PrincipalContextArgumentResolver implements HandlerMethodArgumentResolver {

    @Override
    public boolean supportsParameter(MethodParameter parameter) {
        return PrincipalContext.class.equals(parameter.getParameterType());
    }

    @Override
    public Object resolveArgument(MethodParameter parameter, ModelAndViewContainer mavContainer,
                                  NativeWebRequest webRequest, WebDataBinderFactory binderFactory) {
        HttpServletRequest request = webRequest.getNativeRequest(HttpServletRequest.class);
        Object v = request.getAttribute(BearerAuthFilter.ATTR_PRINCIPAL);
        if (!(v instanceof PrincipalContext ctx)) {
            throw new ApiException(ErrorCode.AUTH_REQUIRED, "authenticated principal required");
        }
        return ctx;
    }
}
