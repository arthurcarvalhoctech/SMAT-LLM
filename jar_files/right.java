public class DiscountCalculator {
    public int discount = -5; // variável de instância
    
    public DiscountCalculator() { }

    public DiscountCalculator(int discount) {
        this.discount = discount;
    }

    public int apply(int price) {
        int finalPrice = price + discount;
        return finalPrice;
    }
}
