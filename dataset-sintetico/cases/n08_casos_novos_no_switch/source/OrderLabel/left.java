package demo;

public class OrderLabel {
    public String label(String status) {
        switch (status) {
            case "NEW":
                return "Novo";
            case "CANCELLED":
                return "Cancelado";
            case "PAID":
                return "Pago";
            default:
                return "Desconhecido";
        }
    }
}
