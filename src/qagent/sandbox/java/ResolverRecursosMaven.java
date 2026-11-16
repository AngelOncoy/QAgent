// Herramienta de QAgent: se ejecuta solo durante el build Docker, nunca en el anfitrión.
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashSet;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.Element;

class ResolverRecursosMaven {
    public static void main(String[] args) throws Exception {
        Path archivo = Path.of(args[0]);
        if (Files.size(archivo) > 16 * 1024 * 1024) {
            throw new IllegalArgumentException("El POM efectivo supera 16 MiB.");
        }
        var fabrica = DocumentBuilderFactory.newInstance();
        fabrica.setNamespaceAware(true);
        fabrica.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
        fabrica.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        fabrica.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        var documento = fabrica.newDocumentBuilder().parse(archivo.toFile());
        var plugins = documento.getElementsByTagNameNS("*", "plugin");
        var artefactos = new LinkedHashSet<String>();
        for (int i = 0; i < plugins.getLength(); i++) {
            var plugin = (Element) plugins.item(i);
            String nombre = "";
            for (var hijo = plugin.getFirstChild(); hijo != null; hijo = hijo.getNextSibling()) {
                if (hijo instanceof Element elemento && elemento.getLocalName().equals("artifactId")) {
                    nombre = elemento.getTextContent().trim();
                }
            }
            if (!nombre.equals("maven-remote-resources-plugin")) continue;
            var recursos = plugin.getElementsByTagNameNS("*", "resourceBundle");
            for (int j = 0; j < recursos.getLength(); j++) {
                String coordenadas = recursos.item(j).getTextContent().trim();
                if (!coordenadas.matches("[A-Za-z0-9_.-]+:[A-Za-z0-9_.-]+:[A-Za-z0-9_.-]+(?::[A-Za-z0-9_.-]+){0,2}")) {
                    throw new IllegalArgumentException("resourceBundle requiere coordenadas Maven explícitas resueltas.");
                }
                artefactos.add(coordenadas);
            }
        }
        for (String artefacto : artefactos) {
            var proceso = new ProcessBuilder("mvn", "org.apache.maven.plugins:maven-dependency-plugin:3.11.0:get", "-Dartifact=" + artefacto);
            proceso.environment().put("MAVEN_OPTS", "");
            if (proceso.inheritIO().start().waitFor() != 0) {
                throw new IllegalStateException("No se pudo descargar resourceBundle " + artefacto);
            }
        }
    }
}
