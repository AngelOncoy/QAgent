package org.qagent.bench.spring;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/** Controlador de referencia: estados declarados y servicio sustituible por MockBean. */
@RestController
@RequestMapping("/api")
public class ArticulosController {
    private final ArticulosService servicio;

    /** Recibe el servicio; el test MVC debe sustituirlo, sin usar servicios reales. */
    public ArticulosController(ArticulosService servicio) {
        this.servicio = servicio;
    }

    /** Crea un artículo; su respuesta HTTP declarada es 201. */
    @PostMapping("/articulos")
    @ResponseStatus(HttpStatus.CREATED)
    public void crear() {
        servicio.guardar();
    }

    /** Declara 201; el banco incluye un defecto intencional para detectarlo. */
    @PostMapping("/articulos-defecto")
    @ResponseStatus(HttpStatus.CREATED)
    public ResponseEntity<Void> crearDefectuoso() {
        servicio.guardar();
        // D-Spring-01: ResponseEntity sobreescribe el estado declarado con 200.
        return ResponseEntity.ok().build();
    }

    /** No especifica un estado verificable: no se debe inventar un caso. */
    @PostMapping("/sin-contrato")
    public ResponseEntity<Void> sinContrato() {
        return ResponseEntity.accepted().build();
    }
}
