package org.openforis.sigrid;

import org.hibernate.SessionFactory;
import org.hibernate.boot.registry.StandardServiceRegistryBuilder;
import org.hibernate.cfg.Configuration;
import org.hibernate.service.ServiceRegistry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class HibernateUtil {

	private HibernateUtil() {
		// Hide constructor
	}

	private static SessionFactory sessionFactory;
	private static Logger logger = LoggerFactory.getLogger(HibernateUtil.class);

	private static SessionFactory buildSessionFactory() {
        try {
            // Create the SessionFactory from hibernate.cfg.xml
        	Configuration configuration = new Configuration();
        	configuration.configure("hibernate.cfg.xml");
        	logger.info("Hibernate Configuration loaded");

        	configuration.addAnnotatedClass(Plot.class);

        	ServiceRegistry serviceRegistry = new StandardServiceRegistryBuilder().applySettings(configuration.getProperties()).build();
        	logger.info("Hibernate serviceRegistry created");

        	return configuration.buildSessionFactory(serviceRegistry);
        }
        catch (Exception ex) {
        	logger.error("Initial SessionFactory creation failed.", ex);
            throw new ExceptionInInitializerError(ex);
        }
    }

	public static SessionFactory getSessionFactory() {
		if(sessionFactory == null) {
			sessionFactory = buildSessionFactory();
		}
        return sessionFactory;
    }
	/*
	public static void main(String[] args) {
		System.out.println( getSessionFactory() );
	}
	*/
}
