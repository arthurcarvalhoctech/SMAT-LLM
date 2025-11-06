public class DiscountCalculator {
    public int discount = -5; // variável de instância

    public DiscountCalculator() { }

    public DiscountCalculator(int discount) {
        this.discount = discount;
    }

    public int apply(int price) {
        if (price > 50) {
            discount = -10; // aplica desconto condicionalmente
        } 

        int finalPrice = price + discount;
        return finalPrice;
    }
}
