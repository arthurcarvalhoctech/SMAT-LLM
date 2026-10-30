package demo;

public class PriceRule {
    public int price(int base) {
        int p = base;
        p = p + 10;
        boolean vip = base > 50;
        if (vip) {
            p = p - 5;
        }
        return p;
    }
}
