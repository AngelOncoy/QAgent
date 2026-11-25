package org.qagent.bench.spring;

import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/** Controlador de referencia con un DTO validado por Bean Validation (#306). */
@RestController
@RequestMapping("/api")
public class PedidosController {
    private final ArticulosService servicio;

    /** Recibe el servicio; el test MVC lo sustituye por un MockBean. */
    public PedidosController(ArticulosService servicio) {
        this.servicio = servicio;
    }

    /** Registra un pedido válido; responde 201. Un pedido inválido es un 400. */
    @PostMapping("/pedidos")
    @ResponseStatus(HttpStatus.CREATED)
    public void crear(@Valid @RequestBody PedidoDto pedido) {
        servicio.guardar();
    }

    /** Declara 201; el banco incluye un defecto intencional para detectarlo. */
    @PostMapping("/pedidos-defecto")
    @ResponseStatus(HttpStatus.CREATED)
    public ResponseEntity<Void> crearDefectuoso(@Valid @RequestBody PedidoDto pedido) {
        servicio.guardar();
        // D-Spring-02: con un pedido válido, ResponseEntity devuelve 200 en vez de 201.
        return ResponseEntity.ok().build();
    }
}
