package demo;

public class OrderLabel {
    public String label(String status) {
        switch (status) {
            case "NEW":
                return "Novo";
            case "PAID":
                return "Pago";
            case "SHIPPED":
                return "Enviado";
            default:
                return "Desconhecido";
        }
    }
}
