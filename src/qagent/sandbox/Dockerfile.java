# Imagen del sandbox para Java: qagent-sandbox:java (#169).
# JDK, Maven, Gradle, JUnit 5, JaCoCo y PIT. Las dependencias del proyecto van en una
# imagen derivada (paso 1, con red: `mvn dependency:go-offline` o el equivalente de
# Gradle) y las pruebas corren sin red (paso 2).
#
# Dónde queda cada cosa:
#   /opt/qagent/m2          repositorio local de Maven (herramientas + dependencias)
#   /opt/qagent/gradle-ro   caché de solo lectura de Gradle (GRADLE_RO_DEP_CACHE)
#   /work/proyecto          copia del proyecto, montada al ejecutar
# Al ejecutar, Maven corre sin red (`-o`) contra /opt/qagent/m2. Gradle usa una carpeta
# de usuario temporal (GRADLE_USER_HOME en /tmp) y lee las dependencias de la caché.
FROM eclipse-temurin:25.0.4.1_1-jdk-noble

ARG MAVEN_VERSION=3.9.16
ARG MAVEN_SHA512=831a8591fe20c8243b1dbe7d71e3244f31d1665b0804b2e825e38cbbe5ce0cafb8338851f90780735568773e0a6cd07bbec107cda0b896b008b861075358b6f6
ARG GRADLE_VERSION=9.8.2
ARG GRADLE_SHA256=21bd5da2de49b642904077f38c0efdc7778e92b3ed0889392dca61b97e389607

ENV MAVEN_HOME=/opt/maven \
    GRADLE_HOME=/opt/gradle \
    MAVEN_ARGS="--batch-mode --no-transfer-progress -Dmaven.repo.local=/opt/qagent/m2" \
    GRADLE_RO_DEP_CACHE=/opt/qagent/gradle-ro \
    GRADLE_USER_HOME=/tmp/gradle \
    GRADLE_OPTS="-Dorg.gradle.daemon=false -Dorg.gradle.welcome=never" \
    PATH=/opt/maven/bin:/opt/gradle/bin:$PATH

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl unzip \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL -o /tmp/maven.tar.gz \
        "https://archive.apache.org/dist/maven/maven-3/${MAVEN_VERSION}/binaries/apache-maven-${MAVEN_VERSION}-bin.tar.gz" \
    && echo "${MAVEN_SHA512}  /tmp/maven.tar.gz" | sha512sum -c - \
    && mkdir -p /opt/maven \
    && tar -xzf /tmp/maven.tar.gz -C /opt/maven --strip-components=1 \
    && curl -fsSL -o /tmp/gradle.zip \
        "https://services.gradle.org/distributions/gradle-${GRADLE_VERSION}-bin.zip" \
    && echo "${GRADLE_SHA256}  /tmp/gradle.zip" | sha256sum -c - \
    && unzip -q /tmp/gradle.zip -d /opt \
    && mv "/opt/gradle-${GRADLE_VERSION}" /opt/gradle \
    && rm /tmp/maven.tar.gz /tmp/gradle.zip

# Proyecto mínimo que usa JUnit 5, JaCoCo y PIT con las versiones fijas de QAgent
# (ver java/calentamiento/pom.xml): al construirlo una vez, todos los plugins y sus
# proveedores quedan en el repositorio local y luego funcionan sin red.
COPY java/ /opt/qagent/java/
RUN cd /opt/qagent/java/calentamiento \
    && mvn verify org.pitest:pitest-maven:mutationCoverage \
    && rm -rf /opt/qagent/java/calentamiento

# La imagen trae el usuario `ubuntu` con uid 1000: se renombra a `sandbox` para que
# todas las imágenes del sandbox usen el mismo usuario.
RUN usermod --login sandbox --move-home --home /home/sandbox ubuntu \
    && groupmod --new-name sandbox ubuntu \
    && mkdir -p /opt/qagent/gradle-ro /work/proyecto /work/tests /out \
    && chown -R sandbox:sandbox /work /out

# Maven extrae la librería nativa de Jansi (colores de consola) y la carga; en el
# sandbox /tmp no permite ejecutar, así que se extrae en la copia del proyecto (que es
# temporal). Las imágenes derivadas lo anulan al construir (`MAVEN_OPTS=`).
ENV MAVEN_OPTS="-Djansi.tmpdir=/work/proyecto"

USER sandbox
WORKDIR /work
