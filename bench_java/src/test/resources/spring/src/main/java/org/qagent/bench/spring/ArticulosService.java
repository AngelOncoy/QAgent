package org.qagent.bench.spring;

/** Dependencia sin implementación real: únicamente se utiliza simulada en el test MVC. */
public interface ArticulosService {
    /** Guarda el artículo; el MockBean no accede a red ni a una base de datos. */
    void guardar();
}
