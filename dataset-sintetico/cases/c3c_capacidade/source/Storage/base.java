package demo;

public class Storage {
    public int used = 4;
    public int capacity = 9;
    public int incoming = 0;
    public boolean hasRoom;

    public void check() {
        hasRoom = used + incoming <= capacity;
    }
}
