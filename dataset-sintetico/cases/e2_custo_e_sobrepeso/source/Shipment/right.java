package demo;

public class Shipment {
    public int weight = 40;
    public int tag = 0;
    public int extra = 60;
    public int cost;
    public boolean oversize;

    public void plan(int base) {
        int p = base;
        boolean vip = base > 50;
        if (vip) {
            p = p - 5;
        }
        p = p * 2;
        cost = p;
        oversize = weight + extra > 100;
    }
}
