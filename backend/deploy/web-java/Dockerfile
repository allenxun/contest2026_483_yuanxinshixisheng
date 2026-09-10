# syntax=docker/dockerfile:1
# 版本锁定（decisions.md）：构建 maven:3.9-eclipse-temurin-21 → 运行 eclipse-temurin:21-jre，Java 21。
# 多阶段：Maven 离线构建 fat jar，仅 JRE 进入运行镜像；非 root 运行，actuator 健康检查。

FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /build
# 先解析依赖（利用层缓存）
COPY pom.xml ./
RUN mvn -B -q -DskipTests dependency:go-offline
COPY src ./src
RUN mvn -B -q -DskipTests package

FROM eclipse-temurin:21-jre AS run
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --create-home --uid 10001 appuser
WORKDIR /app
COPY --from=build /build/target/*.jar app.jar
USER appuser
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
    CMD curl -fsS "http://localhost:${SERVER_PORT:-8080}/actuator/health" || exit 1
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
