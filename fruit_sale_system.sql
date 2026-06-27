-- 用户表
CREATE TABLE users(
	user_id SERIAL PRIMARY KEY, 
	username VARCHAR(50) NOT NULL, 
	password VARCHAR(100) NOT NULL, 
	role VARCHAR(20) NOT NULL CHECK (role IN ('种植户', '采购商', '管理员'))
);

-- 地块表
CREATE TABLE lands(
	land_id SERIAL PRIMARY KEY,
	area NUMERIC(10, 2),
	location VARCHAR(50),
	user_id INT REFERENCES users(user_id)
);

--果蔬表
CREATE TABLE fruits(
	fruit_id SERIAL PRIMARY KEY,
	variety VARCHAR(50) NOT NULL,
	plant_time TIMESTAMP,
	flower_time TIMESTAMP,
	fruit_time TIMESTAMP,
	maturity VARCHAR(20) CHECK (maturity IN ('生长期', '成熟可售')),
	estimated_yield NUMERIC(10, 2) NOT NULL,
	purchased_yield NUMERIC(10, 2),
	price NUMERIC(10, 2),
	land_id INT REFERENCES lands(land_id)
);

--农事记录表
CREATE TABLE records(
	record_id SERIAL PRIMARY KEY, 
	operation_type VARCHAR(20) CHECK (operation_type IN ('施肥', '浇水')), 
	operation_time TIMESTAMP, 
	details VARCHAR(200),
	fruit_id INT REFERENCES fruits(fruit_id)
);

--订单表
CREATE TABLE orders(
	order_id SERIAL PRIMARY KEY,
	amount NUMERIC(10, 2),
	order_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	user_id INT REFERENCES users(user_id),
	fruit_id INT REFERENCES fruits(fruit_id)
);

-- 插入测试数据（
-- 用户
INSERT INTO users (username, password, role) VALUES ('管理员小王', '123', '管理员');
INSERT INTO users (username, password, role) VALUES ('种植户张三', '123', '种植户');
INSERT INTO users (username, password, role) VALUES ('种植户李四', '123', '种植户');
INSERT INTO users (username, password, role) VALUES ('采购商赵六', '123', '采购商');

-- 地块
INSERT INTO lands (area, location, user_id) VALUES (5.0, '城北1号大棚', 2);
INSERT INTO lands (area, location, user_id) VALUES (3.0, '城北2号大棚', 2);
INSERT INTO lands (area, location, user_id) VALUES (4.0, '城南阳光大棚', 3);

-- 果蔬
INSERT INTO fruits (variety, plant_time, flower_time, fruit_time, maturity, estimated_yield, purchased_yield, price, land_id)
VALUES ('红颜草莓', '2026-03-01', '2026-03-20', '2026-04-15', '成熟可售', 1000, 0, 25.0, 1);
INSERT INTO fruits (variety, plant_time, maturity, estimated_yield, purchased_yield, price, land_id)
VALUES ('樱桃番茄', '2026-06-01', '生长期', 500, 0, 15.0, 2);

-- 果蔬
INSERT INTO fruits (variety, plant_time, maturity, estimated_yield, purchased_yield, price, land_id)
VALUES ('水果黄瓜', '2026-05-15', '生长期', 300, 0, 8.0, 3);

-- 农事记录
INSERT INTO records (operation_type, operation_time, details, fruit_id)
VALUES ('施肥', '2026-03-10 08:30:00', '施复合肥 20kg', 1);
INSERT INTO records (operation_type, operation_time, details, fruit_id)
VALUES ('浇水', '2026-03-15 16:00:00', '滴灌 2小时', 1);

-- 农事记录
INSERT INTO records (operation_type, operation_time, details, fruit_id)
VALUES ('施肥', '2026-05-20 09:00:00', '施有机肥 10kg', 3);

-- 订单
INSERT INTO orders (amount, user_id, fruit_id) VALUES (200, 4, 1);


--创建触发器
CREATE OR REPLACE FUNCTION check_purchase_limit()
RETURNS TRIGGER AS $$
DECLARE
    current_purchased NUMERIC;
    estimated_total NUMERIC;
BEGIN

    SELECT purchased_yield, estimated_yield INTO current_purchased, estimated_total
    FROM fruits WHERE fruit_id = NEW.fruit_id;

    IF (current_purchased + NEW.amount) > estimated_total THEN
        RAISE EXCEPTION '超出数量，采购失败';
    END IF;

    UPDATE fruits SET purchased_yield = purchased_yield + NEW.amount
    WHERE fruit_id = NEW.fruit_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

--绑定触发器
DROP TRIGGER IF EXISTS before_order_insert ON orders;
CREATE TRIGGER before_order_insert
BEFORE INSERT ON orders
FOR EACH ROW EXECUTE PROCEDURE check_purchase_limit();

-- 测试触发器
INSERT INTO orders (amount, user_id, fruit_id) VALUES (500, 4, 1);
-- 下面这条会触发异常（700+600=1300 > 1000 预估产量）
-- INSERT INTO orders (amount, user_id, fruit_id) VALUES (600, 4, 1);
