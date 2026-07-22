package example.order;

import java.util.List;

public interface Order {
    void cancelAll();
    void cancelPartially(List<Long> itemIds);
}
