package demo;

public class PriceRule {
    public int price(int base) {
        int p = base;
        boolean vip = base > 50;
        if (vip) {
            p = p - 5;
        }
        return p;
    }
}
